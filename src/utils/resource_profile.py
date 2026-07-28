"""Container-aware resource discovery and adaptive execution budgets.

The engine runs in notebooks, local Python processes, virtual machines, and
containers.  Host-level ``psutil`` values are not sufficient in all of those
environments, so this module resolves one effective memory and CPU profile from
the host, process affinity, and Linux cgroup limits.

Resource profiles control performance choices only.  They must never weaken
SQL semantics or turn resource exhaustion into an incomplete result.
"""

from dataclasses import dataclass, replace
from functools import cached_property, lru_cache
import math
import os
import posixpath
import sys
import threading
import time
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

import psutil


MIB = 1024 ** 2
DEFAULT_QUERY_MEMORY_CEILING_BYTES = 8 * 1024 * MIB
DEFAULT_CACHE_MEMORY_CEILING_BYTES = 2 * 1024 * MIB
DEFAULT_WORKER_CEILING = 4
DEFAULT_CACHE_ENTRY_CEILING = 50_000
_CACHE_ENTRY_LIMIT_CACHE_SIZE = 512


class InsufficientExecutionResourcesError(RuntimeError):
    """The effective environment has no safe capacity for a query."""


@dataclass(frozen=True)
class EffectiveMemorySnapshot:
    """Memory visible to the current process."""

    host_total_bytes: int
    host_available_bytes: int
    effective_limit_bytes: int
    effective_available_bytes: int
    cgroup_limit_bytes: Optional[int] = None
    cgroup_remaining_bytes: Optional[int] = None
    source: str = 'host'

    def __post_init__(self) -> None:
        for field_name in (
            'host_total_bytes',
            'host_available_bytes',
            'effective_limit_bytes',
            'effective_available_bytes',
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")

    @property
    def pressure_ratio(self) -> float:
        if self.effective_limit_bytes <= 0:
            return 1.0
        available = min(
            self.effective_available_bytes,
            self.effective_limit_bytes,
        )
        return max(
            0.0,
            min(1.0, 1.0 - available / self.effective_limit_bytes),
        )


@dataclass(frozen=True)
class EffectiveCPUSnapshot:
    """CPU concurrency visible to the current process."""

    host_logical_cpus: int
    affinity_cpus: int
    effective_cpus: int
    cgroup_quota_cpus: Optional[float] = None
    source: str = 'host'

    def __post_init__(self) -> None:
        for field_name in (
            'host_logical_cpus',
            'affinity_cpus',
            'effective_cpus',
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be at least 1")


@dataclass(frozen=True)
class _CgroupMount:
    """One cgroup mount described by ``/proc/self/mountinfo``."""

    version: str
    root: str
    mount_point: str
    controllers: FrozenSet[str] = frozenset()


class SystemResourceProbe:
    """Read host, affinity, and Linux cgroup memory/CPU constraints."""

    _CGROUP_V1_UNLIMITED = 1 << 60

    def __init__(
        self,
        host_memory_provider: Optional[Callable[[], Any]] = None,
        host_cpu_provider: Optional[Callable[[], Optional[int]]] = None,
        affinity_provider: Optional[Callable[[], Any]] = None,
        text_reader: Optional[Callable[[str], str]] = None,
        cgroup_root: str = '/sys/fs/cgroup',
        proc_cgroup_path: str = '/proc/self/cgroup',
        proc_mountinfo_path: str = '/proc/self/mountinfo',
        host_provider: Optional[Callable[[], Any]] = None,
        enable_cgroup_probe: Optional[bool] = None,
    ) -> None:
        if host_memory_provider is not None and host_provider is not None:
            raise ValueError(
                "Specify only one of host_memory_provider or host_provider"
            )
        self._host_memory_provider = (
            host_memory_provider
            or host_provider
            or psutil.virtual_memory
        )
        self._host_cpu_provider = host_cpu_provider or os.cpu_count
        self._affinity_provider = (
            affinity_provider or self._default_affinity
        )
        self._text_reader = text_reader or self._read_text
        # Native Windows and macOS do not expose Linux cgroups. Injected
        # readers remain enabled so cgroup parsing can be tested portably.
        self._cgroup_probe_enabled = (
            (
                sys.platform.startswith('linux')
                or text_reader is not None
            )
            if enable_cgroup_probe is None
            else bool(enable_cgroup_probe)
        )
        self._cgroup_root = cgroup_root
        self._proc_cgroup_path = proc_cgroup_path
        self._proc_mountinfo_path = proc_mountinfo_path
        # Structural discovery cache (mount table only).  The cgroup mount
        # layout is fixed for the life of a process unless the process is
        # migrated into a different cgroup, which changes /proc/self/cgroup.
        # Limits and usage values are NEVER cached here: every probe still
        # re-reads memory.max/memory.current/cpu.max, so a tightened container
        # limit or a change in memory pressure is always observed.
        self._mounts_cache: Optional[List[_CgroupMount]] = None
        self._mounts_cache_key: Optional[str] = None
        self._dirs_cache: Dict[Tuple[str, str, Optional[str]], List[str]] = {}
        self._dirs_cache_key: Optional[str] = None

    @staticmethod
    def _read_text(path: str) -> str:
        with open(path, 'r') as file_handle:
            return file_handle.read().strip()

    @staticmethod
    def _default_affinity() -> Optional[Any]:
        if hasattr(os, 'sched_getaffinity'):
            return os.sched_getaffinity(0)
        # Windows exposes processor affinity through psutil rather than
        # os.sched_getaffinity. macOS normally has neither API and safely
        # falls back to os.cpu_count in cpu_snapshot().
        try:
            process = psutil.Process()
            cpu_affinity = getattr(process, 'cpu_affinity', None)
            if cpu_affinity is not None:
                return cpu_affinity()
        except (AttributeError, NotImplementedError, OSError, psutil.Error):
            pass
        return None

    def _safe_read(self, path: str) -> Optional[str]:
        try:
            return self._text_reader(path).strip()
        except (OSError, ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_memory_value(
        raw_value: Optional[str],
        *,
        v1: bool = False,
    ) -> Optional[int]:
        if raw_value is None or raw_value == '' or raw_value == 'max':
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        if v1 and value >= SystemResourceProbe._CGROUP_V1_UNLIMITED:
            return None
        return value

    def _process_cgroup_entries(
        self,
        raw_entries: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Parse /proc/self/cgroup.

        ``raw_entries`` lets one caller read the file once and share the text
        across the memory and CPU probes of a single detection, so both halves
        describe the *same* cgroup identity instead of two independent reads.
        Nothing is cached across detections: every detection re-reads the file.
        """
        if raw_entries is None:
            raw_entries = self._safe_read(self._proc_cgroup_path)
        if not raw_entries:
            return []

        entries: List[Tuple[str, str]] = []
        for line in raw_entries.splitlines():
            parts = line.split(':', 2)
            if len(parts) != 3:
                continue
            hierarchy, controllers, relative_path = parts
            if hierarchy == '0' and controllers == '':
                entries.append(('v2', relative_path))
            else:
                controller_set = set(controllers.split(','))
                if 'memory' in controller_set:
                    entries.append(('v1-memory', relative_path))
                if 'cpu' in controller_set or 'cpuacct' in controller_set:
                    entries.append(('v1-cpu', relative_path))
        return entries

    @staticmethod
    def _decode_mount_path(value: str) -> str:
        """Decode the octal escapes used by Linux mountinfo paths."""
        replacements = {
            r'\040': ' ',
            r'\011': '\t',
            r'\012': '\n',
            r'\134': '\\',
        }
        for escaped, decoded in replacements.items():
            value = value.replace(escaped, decoded)
        return value

    def _cgroup_mounts(self) -> List[_CgroupMount]:
        """Return mounted cgroup hierarchies visible to this process.

        A process cgroup path is relative to the hierarchy root recorded in
        mountinfo.  Joining it directly to ``/sys/fs/cgroup`` works for the
        common root-mounted case but fails in cgroup namespaces and for
        non-standard v1 mount points.

        Parsing mountinfo is the single most expensive step of resource
        detection and it is required twice per detect() (once for memory, once
        for CPU).  The parsed table is therefore memoised per probe instance
        and re-validated against /proc/self/cgroup, which is two orders of
        magnitude cheaper to read.  A process moved into a different cgroup
        changes that file and invalidates the cache; the limit and usage values
        themselves are always re-read by the callers.
        """
        cache_key = self._safe_read(self._proc_cgroup_path) or ''
        if (
            self._mounts_cache is not None
            and self._mounts_cache_key == cache_key
        ):
            return self._mounts_cache

        raw_mountinfo = self._safe_read(self._proc_mountinfo_path)
        if not raw_mountinfo:
            self._mounts_cache = []
            self._mounts_cache_key = cache_key
            return []

        mounts: List[_CgroupMount] = []
        for line in raw_mountinfo.splitlines():
            fields = line.split()
            try:
                separator = fields.index('-')
            except ValueError:
                continue
            if separator < 6 or len(fields) <= separator + 3:
                continue

            fs_type = fields[separator + 1]
            if fs_type not in {'cgroup', 'cgroup2'}:
                continue

            root = self._decode_mount_path(fields[3])
            mount_point = self._decode_mount_path(fields[4])
            if fs_type == 'cgroup2':
                mounts.append(
                    _CgroupMount(
                        version='v2',
                        root=root,
                        mount_point=mount_point,
                    )
                )
                continue

            # v1 lists its controllers in the superblock options after the
            # mountinfo separator.  The mount source is included as a
            # compatibility fallback for older/container-specific layouts.
            mount_source = fields[separator + 2]
            super_options = fields[separator + 3]
            controllers = set(super_options.split(','))
            controllers.update(mount_source.split(','))
            controllers.discard('rw')
            controllers.discard('ro')
            controllers.discard('cgroup')
            mounts.append(
                _CgroupMount(
                    version='v1',
                    root=root,
                    mount_point=mount_point,
                    controllers=frozenset(controllers),
                )
            )
        self._mounts_cache = mounts
        self._mounts_cache_key = cache_key
        return mounts

    @staticmethod
    def _directory_in_mount(
        mount: _CgroupMount,
        process_cgroup_path: str,
    ) -> Optional[str]:
        """Map a process hierarchy path to its visible mounted directory."""
        mount_root = posixpath.normpath('/' + mount.root.lstrip('/'))
        process_path = posixpath.normpath(
            '/' + process_cgroup_path.lstrip('/')
        )
        if mount_root == '/':
            relative = process_path.lstrip('/')
        elif process_path == mount_root:
            relative = ''
        elif process_path.startswith(mount_root + '/'):
            relative = process_path[len(mount_root):].lstrip('/')
        else:
            # The mount does not expose this process hierarchy path.
            return None

        mount_point = posixpath.abspath(mount.mount_point)
        resolved = posixpath.abspath(posixpath.join(mount_point, relative))
        try:
            if posixpath.commonpath([mount_point, resolved]) != mount_point:
                return None
        except ValueError:
            return None
        return resolved

    def _mounted_directories(
        self,
        version: str,
        relative_path: str,
        controller: Optional[str] = None,
    ) -> List[str]:
        """Resolve leaf-to-root directories for one cgroup hierarchy.

        Purely structural path arithmetic over the (already memoised) mount
        table.  Memoised under the same /proc/self/cgroup validity key: the
        directory *list* is cached, never the limit or usage values read from
        those directories.
        """
        cache_key = (
            self._mounts_cache_key
            if self._mounts_cache is not None
            else None
        )
        memo_key = (version, relative_path, controller)
        if (
            cache_key is not None
            and self._dirs_cache_key == cache_key
            and memo_key in self._dirs_cache
        ):
            return self._dirs_cache[memo_key]

        directories: List[str] = []
        for mount in self._cgroup_mounts():
            if mount.version != version:
                continue
            if (
                controller is not None
                and controller not in mount.controllers
            ):
                continue
            leaf = self._directory_in_mount(mount, relative_path)
            if leaf is None:
                continue
            directories.extend(
                self._ancestor_directories(
                    mount.mount_point,
                    leaf,
                    path_is_leaf=True,
                )
            )
        resolved = list(dict.fromkeys(directories))
        current_key = self._mounts_cache_key
        if current_key is not None:
            if self._dirs_cache_key != current_key:
                self._dirs_cache = {}
                self._dirs_cache_key = current_key
            self._dirs_cache[memo_key] = resolved
        return resolved

    @staticmethod
    def _ancestor_directories(
        root: str,
        relative_path: str,
        *,
        path_is_leaf: bool = False,
    ) -> List[str]:
        normalized_root = posixpath.abspath(root)
        if path_is_leaf:
            leaf = posixpath.abspath(relative_path)
        else:
            relative = relative_path.lstrip('/')
            leaf = posixpath.abspath(
                posixpath.join(normalized_root, relative)
            )
        try:
            if (
                posixpath.commonpath([normalized_root, leaf])
                != normalized_root
            ):
                return [normalized_root]
        except ValueError:
            return [normalized_root]

        directories = []
        current = leaf
        while True:
            directories.append(current)
            if current == normalized_root:
                break
            parent = posixpath.dirname(current)
            if parent == current:
                break
            current = parent
        return directories

    def _cgroup_memory_constraints(
        self,
        raw_entries: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[int]]:
        if not self._cgroup_probe_enabled:
            return None, None
        candidates: List[Tuple[str, str, bool]] = []
        for version, relative_path in self._process_cgroup_entries(raw_entries):
            if version == 'v2':
                roots = self._mounted_directories(
                    'v2',
                    relative_path,
                )
                if not roots:
                    roots = self._ancestor_directories(
                        self._cgroup_root,
                        relative_path,
                    )
                candidates.extend(
                    (
                        posixpath.join(directory, 'memory.max'),
                        posixpath.join(directory, 'memory.current'),
                        False,
                    )
                    for directory in roots
                )
            elif version == 'v1-memory':
                roots = self._mounted_directories(
                    'v1',
                    relative_path,
                    controller='memory',
                )
                if not roots:
                    root = posixpath.join(self._cgroup_root, 'memory')
                    roots = self._ancestor_directories(
                        root,
                        relative_path,
                    )
                candidates.extend(
                    (
                        posixpath.join(
                            directory,
                            'memory.limit_in_bytes',
                        ),
                        posixpath.join(
                            directory,
                            'memory.usage_in_bytes',
                        ),
                        True,
                    )
                    for directory in roots
                )

        # Root-level fallbacks.  These exist for the case where the process
        # hierarchy could not be resolved at all (no /proc, unparsable
        # mountinfo, unknown layout).  When resolution succeeded the ancestor
        # walk already includes the hierarchy root, so probing these again only
        # repeats reads that cannot contribute a new minimum.  Keeping them
        # conditional preserves the safety net exactly while removing the
        # redundant syscalls from the common path.
        if not candidates:
            candidates.extend([
                (
                    posixpath.join(self._cgroup_root, 'memory.max'),
                    posixpath.join(self._cgroup_root, 'memory.current'),
                    False,
                ),
                (
                    posixpath.join(
                        self._cgroup_root,
                        'memory',
                        'memory.limit_in_bytes',
                    ),
                    posixpath.join(
                        self._cgroup_root,
                        'memory',
                        'memory.usage_in_bytes',
                    ),
                    True,
                ),
            ])

        limits: List[int] = []
        remaining_values: List[int] = []
        seen = set()
        for limit_path, usage_path, is_v1 in candidates:
            key = (limit_path, usage_path)
            if key in seen:
                continue
            seen.add(key)

            limit = self._parse_memory_value(
                self._safe_read(limit_path),
                v1=is_v1,
            )
            if limit is None:
                continue
            limits.append(limit)
            usage = self._parse_memory_value(self._safe_read(usage_path))
            # A known limit with unknown usage cannot establish safe remaining
            # capacity. Fail closed rather than treating the whole cgroup
            # allowance as free and risking an OOM kill.
            remaining_values.append(
                0 if usage is None else max(0, limit - usage)
            )

        return (
            min(limits) if limits else None,
            min(remaining_values) if remaining_values else None,
        )

    def memory_snapshot(
        self,
        raw_entries: Optional[str] = None,
    ) -> EffectiveMemorySnapshot:
        host = self._host_memory_provider()
        host_total = max(0, int(host.total))
        host_available = max(0, int(host.available))
        cgroup_limit, cgroup_remaining = (
            self._cgroup_memory_constraints(raw_entries)
        )

        effective_limit = host_total
        effective_available = host_available
        source = 'host'
        if cgroup_limit is not None:
            effective_limit = min(effective_limit, cgroup_limit)
            source = 'host+cgroup'
        if cgroup_remaining is not None:
            effective_available = min(
                effective_available,
                cgroup_remaining,
            )
            source = 'host+cgroup'
        effective_available = min(effective_available, effective_limit)

        return EffectiveMemorySnapshot(
            host_total_bytes=host_total,
            host_available_bytes=host_available,
            cgroup_limit_bytes=cgroup_limit,
            cgroup_remaining_bytes=cgroup_remaining,
            effective_limit_bytes=effective_limit,
            effective_available_bytes=effective_available,
            source=source,
        )

    def snapshot(self) -> EffectiveMemorySnapshot:
        """Compatibility shorthand for memory-only consumers."""
        return self.memory_snapshot()

    @staticmethod
    def _parse_cpu_max(raw_value: Optional[str]) -> Optional[float]:
        if not raw_value:
            return None
        parts = raw_value.split()
        if len(parts) != 2 or parts[0] == 'max':
            return None
        try:
            quota = int(parts[0])
            period = int(parts[1])
        except ValueError:
            return None
        if quota <= 0 or period <= 0:
            return None
        return quota / period

    def _cgroup_cpu_quota(
        self,
        raw_entries: Optional[str] = None,
    ) -> Optional[float]:
        if not self._cgroup_probe_enabled:
            return None
        quotas: List[float] = []
        v2_directories: List[str] = []
        v1_directories: List[str] = []
        for version, relative_path in self._process_cgroup_entries(raw_entries):
            if version == 'v2':
                resolved = self._mounted_directories(
                    'v2',
                    relative_path,
                )
                v2_directories.extend(
                    resolved
                    or self._ancestor_directories(
                        self._cgroup_root,
                        relative_path,
                    )
                )
            elif version == 'v1-cpu':
                resolved = self._mounted_directories(
                    'v1',
                    relative_path,
                    controller='cpu',
                )
                if resolved:
                    v1_directories.extend(resolved)
                else:
                    for cpu_root_name in ('cpu', 'cpu,cpuacct'):
                        v1_directories.extend(
                            self._ancestor_directories(
                                posixpath.join(
                                    self._cgroup_root,
                                    cpu_root_name,
                                ),
                                relative_path,
                            )
                        )

        # Same rule as the memory probe: the root-level fallbacks are only a
        # net for an unresolvable hierarchy.  When the process hierarchy did
        # resolve, its ancestor walk already reaches the mount root, so these
        # extra probes cannot lower the quota and are pure syscall cost.
        if not v2_directories and not v1_directories:
            v2_directories.append(self._cgroup_root)
            v1_directories.extend([
                posixpath.join(self._cgroup_root, 'cpu'),
                posixpath.join(self._cgroup_root, 'cpu,cpuacct'),
            ])
        for directory in dict.fromkeys(v2_directories):
            quota = self._parse_cpu_max(
                self._safe_read(posixpath.join(directory, 'cpu.max'))
            )
            if quota is not None:
                quotas.append(quota)

        for directory in dict.fromkeys(v1_directories):
            quota_raw = self._safe_read(
                posixpath.join(directory, 'cpu.cfs_quota_us')
            )
            period_raw = self._safe_read(
                posixpath.join(directory, 'cpu.cfs_period_us')
            )
            try:
                quota_value = int(quota_raw) if quota_raw is not None else -1
                period_value = (
                    int(period_raw) if period_raw is not None else 0
                )
            except ValueError:
                continue
            if quota_value > 0 and period_value > 0:
                quotas.append(quota_value / period_value)

        return min(quotas) if quotas else None

    def cpu_snapshot(
        self,
        raw_entries: Optional[str] = None,
    ) -> EffectiveCPUSnapshot:
        host_cpus = max(1, int(self._host_cpu_provider() or 1))
        affinity_applied = False
        try:
            affinity = self._affinity_provider()
            if affinity is None:
                affinity_cpus = host_cpus
            else:
                candidate_count = len(affinity)
                if candidate_count < 1:
                    affinity_cpus = host_cpus
                else:
                    affinity_cpus = candidate_count
                    affinity_applied = True
        except (OSError, TypeError, ValueError):
            affinity_cpus = host_cpus
        affinity_cpus = max(1, min(host_cpus, int(affinity_cpus)))

        quota = self._cgroup_cpu_quota(raw_entries)
        effective = affinity_cpus
        source_parts = ['host']
        if affinity_applied:
            source_parts.append('affinity')
        if quota is not None:
            # Worker pools use an integer concurrency.  Flooring prevents a
            # fractional quota from causing persistent CPU oversubscription.
            quota_workers = max(1, int(math.floor(quota)))
            effective = min(effective, quota_workers)
            source_parts.append('cgroup')

        return EffectiveCPUSnapshot(
            host_logical_cpus=host_cpus,
            affinity_cpus=affinity_cpus,
            cgroup_quota_cpus=quota,
            effective_cpus=max(1, effective),
            source='+'.join(source_parts),
        )


# Compatibility name retained for the DFA builder and existing callers.
SystemMemoryProbe = SystemResourceProbe


_default_probe_lock = threading.Lock()
_default_probe_instance: Optional[SystemResourceProbe] = None


def _default_probe() -> SystemResourceProbe:
    """Process-wide probe holding only the structural cgroup caches."""
    global _default_probe_instance
    probe = _default_probe_instance
    if probe is None:
        with _default_probe_lock:
            if _default_probe_instance is None:
                _default_probe_instance = SystemResourceProbe()
            probe = _default_probe_instance
    return probe


def reset_default_probe() -> None:
    """Drop the shared probe (and its structural caches); for tests."""
    global _default_probe_instance
    with _default_probe_lock:
        _default_probe_instance = None


@lru_cache(maxsize=_CACHE_ENTRY_LIMIT_CACHE_SIZE)
def _cached_cache_entry_limit(
    cache_budget_bytes: int,
    estimated_entry_bytes: int,
    budget_share: float,
    effective_maximum: int,
) -> int:
    """Resolve a cache limit from immutable primitive budget values."""
    component_budget = int(cache_budget_bytes * budget_share)
    affordable_entries = component_budget // estimated_entry_bytes
    if affordable_entries < 1:
        return 0
    return min(effective_maximum, affordable_entries)


@dataclass(frozen=True)
class AdaptiveResourceProfile:
    """Frozen resource budgets used by one component or query."""

    memory: EffectiveMemorySnapshot
    cpu: EffectiveCPUSnapshot
    reserve_fraction: float = 0.10
    reserve_floor_bytes: int = 512 * MIB
    cache_available_fraction: float = 0.10
    cache_limit_fraction: float = 0.05
    cache_hard_max_bytes: Optional[int] = (
        DEFAULT_CACHE_MEMORY_CEILING_BYTES
    )
    query_available_fraction: float = 0.50
    query_limit_fraction: float = 0.25
    query_hard_max_bytes: Optional[int] = (
        DEFAULT_QUERY_MEMORY_CEILING_BYTES
    )
    worker_hard_max: Optional[int] = DEFAULT_WORKER_CEILING
    cache_entry_hard_max: Optional[int] = DEFAULT_CACHE_ENTRY_CEILING

    def __post_init__(self) -> None:
        for field_name in (
            'reserve_fraction',
            'cache_available_fraction',
            'cache_limit_fraction',
            'query_available_fraction',
            'query_limit_fraction',
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")
        if self.reserve_floor_bytes < 0:
            raise ValueError("reserve_floor_bytes cannot be negative")
        if (
            self.cache_hard_max_bytes is not None
            and self.cache_hard_max_bytes < 0
        ):
            raise ValueError(
                "cache_hard_max_bytes cannot be negative"
            )
        if (
            self.query_hard_max_bytes is not None
            and self.query_hard_max_bytes < 1
        ):
            raise ValueError("query_hard_max_bytes must be at least 1")
        if self.worker_hard_max is not None and self.worker_hard_max < 1:
            raise ValueError("worker_hard_max must be at least 1")
        if (
            self.cache_entry_hard_max is not None
            and self.cache_entry_hard_max < 0
        ):
            raise ValueError("cache_entry_hard_max cannot be negative")

    @classmethod
    def detect(
        cls,
        probe: Optional[SystemResourceProbe] = None,
    ) -> 'AdaptiveResourceProfile':
        # A fresh probe would discard the memoised cgroup mount/dir tables on
        # every call, so the default path reuses one process-wide probe.  The
        # probe caches *structure* only (mount table and resolved directory
        # lists, both validated against /proc/self/cgroup); every limit, usage
        # and affinity value is still read live on each detect().  Callers that
        # pass an explicit probe -- tests and mocked platforms -- are unaffected.
        resolved_probe = probe or _default_probe()
        # Read the process cgroup identity once and share it with both halves
        # of this detection: one file read instead of two, and a coherent
        # snapshot (memory and CPU describe the same cgroup).  This is a
        # per-detection read, never a cross-detection cache.
        shared_entries = resolved_probe._safe_read(
            resolved_probe._proc_cgroup_path
        )
        profile = cls(
            memory=resolved_probe.memory_snapshot(shared_entries),
            cpu=resolved_probe.cpu_snapshot(shared_entries),
        )
        return profile.with_environment_ceilings()

    @staticmethod
    def _environment_integer(
        name: str,
        *,
        allow_zero: bool = False,
    ) -> Optional[int]:
        raw_value = os.getenv(name)
        if raw_value is None:
            return None
        try:
            value = int(raw_value)
        except ValueError as error:
            requirement = "non-negative" if allow_zero else "positive"
            raise ValueError(
                f"{name} must be a {requirement} integer"
            ) from error
        minimum = 0 if allow_zero else 1
        if value < minimum:
            requirement = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{name} must be a {requirement} integer")
        return value

    def with_environment_ceilings(self) -> 'AdaptiveResourceProfile':
        """Apply administrator ceilings to every resource consumer.

        These values never increase a detected budget.  Placing them on the
        shared immutable profile prevents a configuration value from being
        observed by the executor but ignored by a cache, worker pool, matcher,
        or automaton builder that reads the profile directly.
        """
        query_mb = self._environment_integer('MR_MAX_MEMORY_MB')
        cache_mb = self._environment_integer(
            'MR_CACHE_MEMORY_LIMIT_MB',
            allow_zero=True,
        )
        workers = self._environment_integer('MR_MAX_WORKERS')
        cache_entries = self._environment_integer(
            'MR_CACHE_SIZE_LIMIT',
            allow_zero=True,
        )

        def lower_ceiling(
            current: Optional[int],
            requested: Optional[int],
        ) -> Optional[int]:
            if requested is None:
                return current
            if current is None:
                return requested
            return min(current, requested)

        return replace(
            self,
            query_hard_max_bytes=lower_ceiling(
                self.query_hard_max_bytes,
                None if query_mb is None else query_mb * MIB,
            ),
            cache_hard_max_bytes=lower_ceiling(
                self.cache_hard_max_bytes,
                None if cache_mb is None else cache_mb * MIB,
            ),
            worker_hard_max=lower_ceiling(
                self.worker_hard_max,
                workers,
            ),
            cache_entry_hard_max=lower_ceiling(
                self.cache_entry_hard_max,
                cache_entries,
            ),
        )

    @cached_property
    def reserved_headroom_bytes(self) -> int:
        requested = max(
            self.reserve_floor_bytes,
            int(
                self.memory.effective_limit_bytes
                * self.reserve_fraction
            ),
        )
        return min(
            requested,
            self.memory.effective_available_bytes // 2,
        )

    @cached_property
    def usable_available_bytes(self) -> int:
        return max(
            0,
            self.memory.effective_available_bytes
            - self.reserved_headroom_bytes,
        )

    @cached_property
    def cache_budget_bytes(self) -> int:
        candidates = [
            int(
                self.usable_available_bytes
                * self.cache_available_fraction
            ),
            int(
                self.memory.effective_limit_bytes
                * self.cache_limit_fraction
            ),
        ]
        if self.cache_hard_max_bytes is not None:
            candidates.append(self.cache_hard_max_bytes)
        # Caching is optional.  When no byte can be reserved safely, expose
        # zero capacity so callers disable the cache instead of inventing a
        # one-entry allocation outside the detected resource ceiling.
        return max(0, min(candidates))

    @cached_property
    def query_budget_bytes(self) -> int:
        candidates = [
            int(
                self.usable_available_bytes
                * self.query_available_fraction
            ),
            int(
                self.memory.effective_limit_bytes
                * self.query_limit_fraction
            ),
            # Cache and query allocations coexist.  This final candidate
            # prevents independently configured fractions from promising
            # more memory than remains after the shared cache pool.
            max(0, self.usable_available_bytes - self.cache_budget_bytes),
        ]
        if self.query_hard_max_bytes is not None:
            candidates.append(self.query_hard_max_bytes)
        return max(0, min(candidates))

    def require_query_capacity(self, minimum_bytes: int = 1) -> None:
        if minimum_bytes < 1:
            raise ValueError("minimum_bytes must be at least 1")
        if self.query_budget_bytes < minimum_bytes:
            raise InsufficientExecutionResourcesError(
                "No safe query-memory capacity remains in the effective "
                f"{self.memory.source} environment "
                f"(available={self.memory.effective_available_bytes} bytes, "
                f"reserved={self.reserved_headroom_bytes} bytes)."
            )

    def worker_count(
        self,
        requested: Optional[int] = None,
        *,
        estimated_bytes_per_worker: int = 256 * MIB,
        reserve_one_cpu: bool = False,
    ) -> int:
        if estimated_bytes_per_worker < 1:
            raise ValueError(
                "estimated_bytes_per_worker must be at least 1"
            )
        cpu_limit = self.cpu.effective_cpus
        if self.worker_hard_max is not None:
            cpu_limit = min(cpu_limit, self.worker_hard_max)
        if reserve_one_cpu and cpu_limit > 1:
            cpu_limit -= 1
        memory_limit = max(
            1,
            self.query_budget_bytes // estimated_bytes_per_worker,
        )
        resolved = min(cpu_limit, memory_limit)
        if requested is not None:
            if requested < 1:
                raise ValueError("requested workers must be at least 1")
            resolved = min(resolved, requested)
        return max(1, resolved)

    def cache_entry_limit(
        self,
        estimated_entry_bytes: int,
        *,
        budget_share: float = 0.05,
        minimum: int = 32,
        maximum: int = 500_000,
    ) -> int:
        if estimated_entry_bytes < 1:
            raise ValueError("estimated_entry_bytes must be at least 1")
        if not 0.0 < budget_share <= 1.0:
            raise ValueError("budget_share must be between 0 and 1")
        if minimum < 1 or maximum < minimum:
            raise ValueError("invalid cache entry bounds")
        if self.cache_entry_hard_max is not None:
            maximum = min(maximum, self.cache_entry_hard_max)
        return _cached_cache_entry_limit(
            self.cache_budget_bytes,
            estimated_entry_bytes,
            budget_share,
            maximum,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            'effective_memory_limit_bytes':
                self.memory.effective_limit_bytes,
            'effective_memory_available_bytes':
                self.memory.effective_available_bytes,
            'memory_source': self.memory.source,
            'effective_cpus': self.cpu.effective_cpus,
            'cpu_source': self.cpu.source,
            'reserved_headroom_bytes': self.reserved_headroom_bytes,
            'query_budget_bytes': self.query_budget_bytes,
            'cache_budget_bytes': self.cache_budget_bytes,
            'query_hard_max_bytes': self.query_hard_max_bytes,
            'cache_hard_max_bytes': self.cache_hard_max_bytes,
            'worker_hard_max': self.worker_hard_max,
            'cache_entry_hard_max': self.cache_entry_hard_max,
        }


_profile_lock = threading.RLock()
_cached_profile: Optional[AdaptiveResourceProfile] = None
_cached_profile_at = 0.0


def get_adaptive_resource_profile(
    *,
    refresh: bool = False,
    max_age_seconds: float = 1.0,
) -> AdaptiveResourceProfile:
    """Return a short-lived profile so pressure changes are observed safely."""
    global _cached_profile, _cached_profile_at
    now = time.monotonic()

    # This function is called while constructing row and expression contexts.
    # Those objects may be created many times during a large query.  Reading a
    # fully constructed immutable profile is safe without taking the refresh
    # lock; the lock is needed only by the thread that replaces the snapshot.
    # A second check inside the lock handles a concurrent refresh.
    cached = _cached_profile
    cached_at = _cached_profile_at
    if (
        not refresh
        and cached is not None
        and now - cached_at < max_age_seconds
    ):
        return cached

    with _profile_lock:
        if (
            refresh
            or _cached_profile is None
            or now - _cached_profile_at >= max_age_seconds
        ):
            _cached_profile = AdaptiveResourceProfile.detect()
            _cached_profile_at = now
        return _cached_profile


def reset_adaptive_resource_profile_cache() -> None:
    """Clear the process-wide profile cache (primarily for tests)."""
    global _cached_profile, _cached_profile_at
    with _profile_lock:
        _cached_profile = None
        _cached_profile_at = 0.0
