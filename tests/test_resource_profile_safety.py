"""Machine-independent resource-detection safety tests.

Promoted from the external adaptive-engine safety harness.  Every test drives
``SystemResourceProbe`` through injected providers and a fake text reader, so
none of them depend on the host's real cgroup layout, CPU count or memory size,
and none of them assert on timing.
"""

import os

import pytest

from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    EffectiveCPUSnapshot,
    EffectiveMemorySnapshot,
    InsufficientExecutionResourcesError,
    SystemResourceProbe,
)

MIB = 1024 ** 2
V2_MOUNTINFO = "30 23 0:26 / /sys/fs/cgroup rw,nosuid - cgroup2 cgroup2 rw\n"
V1_MOUNTINFO = (
    "31 23 0:27 / /sys/fs/cgroup/memory rw - cgroup cgroup rw,memory\n"
    "32 23 0:28 / /sys/fs/cgroup/cpu,cpuacct rw - cgroup cgroup rw,cpu,cpuacct\n"
)


class _FakeMemory:
    def __init__(self, total, available):
        self.total = total
        self.available = available


def build_probe(files=None, cgroup="0::/mygroup\n", mountinfo=V2_MOUNTINFO,
                affinity=None, cpus=8, total=64 * 1024 * MIB,
                available=32 * 1024 * MIB, reader=None):
    """A probe whose entire view of the world is injected."""
    store = dict(files or {})
    store['/proc/self/cgroup'] = cgroup
    store['/proc/self/mountinfo'] = mountinfo

    def default_reader(path):
        if path in store:
            return store[path]
        raise FileNotFoundError(path)

    probe = SystemResourceProbe(
        host_memory_provider=lambda: _FakeMemory(total, available),
        host_cpu_provider=lambda: cpus,
        affinity_provider=(lambda: affinity),
        text_reader=reader or default_reader,
    )
    return probe, store


def test_host_only_detection_without_cgroup_files():
    probe, _ = build_probe()
    snapshot = probe.memory_snapshot()
    assert snapshot.effective_limit_bytes == 64 * 1024 * MIB
    assert snapshot.source == 'host'
    assert snapshot.effective_available_bytes > 0


def test_cgroup_v2_memory_limit_is_applied():
    probe, _ = build_probe({
        '/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB),
        '/sys/fs/cgroup/mygroup/memory.current': str(1024 * MIB),
    })
    snapshot = probe.memory_snapshot()
    assert snapshot.effective_limit_bytes == 8 * 1024 * MIB
    assert snapshot.cgroup_limit_bytes == 8 * 1024 * MIB
    assert 'cgroup' in snapshot.source


def test_cgroup_v1_memory_limit_is_applied():
    probe, _ = build_probe(
        {'/sys/fs/cgroup/memory/v1grp/memory.limit_in_bytes': str(3 * 1024 * MIB)},
        cgroup="4:memory:/v1grp\n5:cpu,cpuacct:/v1grp\n",
        mountinfo=V1_MOUNTINFO,
    )
    assert probe.memory_snapshot().effective_limit_bytes == 3 * 1024 * MIB


def test_cgroup_v1_unlimited_sentinel_is_ignored():
    probe, _ = build_probe(
        {'/sys/fs/cgroup/memory/v1grp/memory.limit_in_bytes': str(1 << 62)},
        cgroup="4:memory:/v1grp\n",
        mountinfo=V1_MOUNTINFO,
    )
    snapshot = probe.memory_snapshot()
    assert snapshot.cgroup_limit_bytes is None
    assert snapshot.effective_limit_bytes == 64 * 1024 * MIB


def test_invalid_numeric_content_is_ignored():
    probe, _ = build_probe({'/sys/fs/cgroup/mygroup/memory.max': 'not-a-number'})
    assert probe.memory_snapshot().cgroup_limit_bytes is None


@pytest.mark.parametrize("value", ['max', '', '-1'])
def test_non_binding_memory_values_fall_back_to_host(value):
    probe, _ = build_probe({'/sys/fs/cgroup/mygroup/memory.max': value})
    assert probe.memory_snapshot().effective_limit_bytes == 64 * 1024 * MIB


def test_permission_error_degrades_to_host_values():
    def denying_reader(path):
        if path == '/proc/self/cgroup':
            return "0::/mygroup\n"
        if path == '/proc/self/mountinfo':
            return V2_MOUNTINFO
        raise PermissionError(path)

    probe, _ = build_probe(reader=denying_reader)
    assert probe.memory_snapshot().effective_limit_bytes == 64 * 1024 * MIB
    assert probe.cpu_snapshot().effective_cpus >= 1


def test_missing_proc_filesystem_is_survivable():
    def absent_reader(path):
        raise FileNotFoundError(path)

    probe, _ = build_probe(reader=absent_reader, cpus=4,
                           total=16 * 1024 * MIB, available=8 * 1024 * MIB)
    memory = probe.memory_snapshot()
    assert memory.effective_limit_bytes == 16 * 1024 * MIB
    assert memory.source == 'host'
    assert probe.cpu_snapshot().effective_cpus == 4


def test_non_linux_platform_falls_back_to_portable_host_providers():
    """Windows/macOS have no Linux procfs or cgroup hierarchy."""
    def absent_reader(path):
        raise FileNotFoundError(path)

    probe = SystemResourceProbe(
        host_memory_provider=lambda: _FakeMemory(
            32 * 1024 * MIB,
            20 * 1024 * MIB,
        ),
        host_cpu_provider=lambda: 8,
        affinity_provider=lambda: None,
        text_reader=absent_reader,
        enable_cgroup_probe=False,
    )

    memory = probe.memory_snapshot()
    cpu = probe.cpu_snapshot()
    assert memory.source == 'host'
    assert memory.effective_limit_bytes == 32 * 1024 * MIB
    assert memory.effective_available_bytes == 20 * 1024 * MIB
    assert cpu.source == 'host'
    assert cpu.effective_cpus == 8


def test_known_cgroup_limit_with_unknown_usage_fails_closed():
    probe, _ = build_probe({
        '/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB),
    })

    snapshot = probe.memory_snapshot()
    assert snapshot.effective_limit_bytes == 8 * 1024 * MIB
    assert snapshot.effective_available_bytes == 0
    with pytest.raises(InsufficientExecutionResourcesError):
        _profile_from(probe).require_query_capacity()


def test_cpu_quota_limits_effective_cpus():
    probe, _ = build_probe({'/sys/fs/cgroup/mygroup/cpu.max': '200000 100000'}, cpus=16)
    snapshot = probe.cpu_snapshot()
    assert snapshot.cgroup_quota_cpus == pytest.approx(2.0)
    assert snapshot.effective_cpus == 2


def test_cpu_affinity_limits_effective_cpus():
    probe, _ = build_probe(affinity={0, 1, 2}, cpus=16)
    assert probe.cpu_snapshot().effective_cpus == 3


def test_cpu_detection_failure_never_yields_zero():
    def absent_reader(path):
        raise OSError(path)

    probe = SystemResourceProbe(
        host_memory_provider=lambda: _FakeMemory(MIB, MIB),
        host_cpu_provider=lambda: None,
        affinity_provider=lambda: None,
        text_reader=absent_reader,
    )
    assert probe.cpu_snapshot().effective_cpus >= 1


def test_memory_detection_never_yields_negative_or_zero_limit():
    probe, _ = build_probe(total=MIB, available=0)
    snapshot = probe.memory_snapshot()
    assert snapshot.effective_limit_bytes > 0
    assert snapshot.effective_available_bytes >= 0


def test_reduced_cgroup_limit_is_observed_on_the_same_probe():
    """Structural caching must never hide a tightened container limit."""
    probe, store = build_probe({
        '/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB),
        '/sys/fs/cgroup/mygroup/memory.current': str(1024 * MIB),
    })
    assert probe.memory_snapshot().effective_limit_bytes == 8 * 1024 * MIB
    store['/sys/fs/cgroup/mygroup/memory.max'] = str(2 * 1024 * MIB)
    assert probe.memory_snapshot().effective_limit_bytes == 2 * 1024 * MIB


def test_raised_cgroup_limit_cannot_exceed_host_memory():
    probe, store = build_probe({'/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB)})
    store['/sys/fs/cgroup/mygroup/memory.max'] = str(999 * 1024 * MIB)
    assert probe.memory_snapshot().effective_limit_bytes == 64 * 1024 * MIB


def test_reduced_cpu_quota_is_observed_on_the_same_probe():
    probe, store = build_probe({'/sys/fs/cgroup/mygroup/cpu.max': '400000 100000'}, cpus=16)
    assert probe.cpu_snapshot().effective_cpus == 4
    store['/sys/fs/cgroup/mygroup/cpu.max'] = '100000 100000'
    assert probe.cpu_snapshot().effective_cpus == 1


def test_cgroup_migration_invalidates_cached_structure():
    probe, store = build_probe({'/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB)})
    assert probe.memory_snapshot().effective_limit_bytes == 8 * 1024 * MIB
    store['/proc/self/cgroup'] = "0::/othergroup\n"
    store['/sys/fs/cgroup/othergroup/memory.max'] = str(4 * 1024 * MIB)
    assert probe.memory_snapshot().effective_limit_bytes == 4 * 1024 * MIB


def test_resource_files_disappearing_after_success_falls_back_safely():
    probe, store = build_probe({'/sys/fs/cgroup/mygroup/memory.max': str(8 * 1024 * MIB)})
    assert probe.memory_snapshot().effective_limit_bytes == 8 * 1024 * MIB
    del store['/sys/fs/cgroup/mygroup/memory.max']
    snapshot = probe.memory_snapshot()
    assert snapshot.effective_limit_bytes == 64 * 1024 * MIB
    assert snapshot.effective_limit_bytes > 0


def _profile_from(probe):
    return AdaptiveResourceProfile(
        memory=probe.memory_snapshot(), cpu=probe.cpu_snapshot())


def test_environment_variable_lowers_the_query_budget(monkeypatch):
    probe, _ = build_probe()
    monkeypatch.setenv('MR_MAX_MEMORY_MB', '512')
    profile = _profile_from(probe).with_environment_ceilings()
    assert profile.query_budget_bytes <= 512 * MIB


def test_environment_variable_cannot_raise_beyond_detected_capacity(monkeypatch):
    probe, _ = build_probe()
    base = _profile_from(probe)
    monkeypatch.setenv('MR_MAX_MEMORY_MB', str(10 ** 9))
    raised = base.with_environment_ceilings()
    assert raised.query_budget_bytes <= base.query_budget_bytes


def test_removing_environment_override_restores_detected_budget(monkeypatch):
    probe, _ = build_probe()
    base = _profile_from(probe)
    monkeypatch.setenv('MR_MAX_MEMORY_MB', '256')
    assert base.with_environment_ceilings().query_budget_bytes <= 256 * MIB
    monkeypatch.delenv('MR_MAX_MEMORY_MB')
    assert base.with_environment_ceilings().query_budget_bytes == base.query_budget_bytes


def test_invalid_environment_value_is_rejected_explicitly(monkeypatch):
    probe, _ = build_probe()
    monkeypatch.setenv('MR_MAX_MEMORY_MB', 'plenty')
    with pytest.raises(ValueError):
        _profile_from(probe).with_environment_ceilings()


def test_query_profile_is_immutable():
    probe, _ = build_probe()
    profile = _profile_from(probe)
    with pytest.raises(Exception):
        profile.reserve_fraction = 0.9


def test_insufficient_capacity_raises_explicitly():
    profile = AdaptiveResourceProfile(
        memory=EffectiveMemorySnapshot(
            host_total_bytes=MIB, host_available_bytes=0,
            effective_limit_bytes=MIB, effective_available_bytes=0),
        cpu=EffectiveCPUSnapshot(
            host_logical_cpus=1, affinity_cpus=1, effective_cpus=1),
    )
    with pytest.raises(InsufficientExecutionResourcesError):
        profile.require_query_capacity(1)


def test_worker_count_and_cache_limits_stay_within_the_profile():
    probe, _ = build_probe({'/sys/fs/cgroup/mygroup/cpu.max': '200000 100000'}, cpus=16)
    profile = _profile_from(probe)
    assert 1 <= profile.worker_count() <= profile.cpu.effective_cpus
    assert profile.cache_entry_limit(1024) >= 0
    assert profile.cache_budget_bytes >= 0
    assert profile.query_budget_bytes >= 0
