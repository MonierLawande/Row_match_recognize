# test_utils.py
"""
Utility functions and base classes for aggregation testing.

This module provides common utilities, mock functions, and base classes
for testing the row pattern matching aggregation functionality.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
import logging
from types import SimpleNamespace

import pytest

from src.utils.resource_profile import (
    AdaptiveResourceProfile,
    EffectiveCPUSnapshot,
    EffectiveMemorySnapshot,
    InsufficientExecutionResourcesError,
    SystemResourceProbe,
)

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockMatchRecognize:
    """
    Mock implementation of match_recognize for testing when the real implementation isn't available.
    
    This class provides basic functionality to validate test structure and data flow
    without requiring the full implementation.
    """
    
    def __init__(self):
        self.call_count = 0
        self.last_query = None
        self.last_dataframe = None
    
    def __call__(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Mock match_recognize function."""
        self.call_count += 1
        self.last_query = query
        self.last_dataframe = df.copy()
        
        logger.info(f"Mock match_recognize called (#{self.call_count})")
        logger.debug(f"Query: {query[:100]}...")
        logger.debug(f"DataFrame shape: {df.shape}")
        
        # Return a basic result structure for testing
        return self._generate_mock_result(df)
    
    def _generate_mock_result(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate a mock result based on the input DataFrame."""
        # Create a simple result with running aggregations
        result_data = {}
        
        # Add basic columns
        if 'id' in df.columns:
            result_data['id'] = df['id'].tolist()
        
        # Add mock aggregation columns based on common patterns
        if 'value' in df.columns:
            values = df['value'].fillna(0)
            result_data['running_sum'] = values.cumsum().tolist()
            result_data['running_avg'] = values.expanding().mean().tolist()
            result_data['running_count'] = list(range(1, len(df) + 1))
        
        # Add classifier if pattern-like queries
        if 'CLASSIFIER()' in self.last_query.upper():
            result_data['classifier'] = ['A'] * len(df)
        
        return pd.DataFrame(result_data)


class TestDefineOptimizerCacheBounds:
    """Global DEFINE planning must have a finite, collision-safe lifetime."""

    def test_cache_is_lru_bounded_and_uses_canonical_definition_keys(self):
        from src.utils.performance_optimizer import DefineOptimizer

        profile = SimpleNamespace(
            cache_entry_limit=lambda **_kwargs: 2,
        )
        optimizer = DefineOptimizer(resource_profile=profile)
        definitions = [
            {"A": "value > 0"},
            {"A": "value > 1"},
            {"A": "value > 2"},
        ]

        optimizer.optimize_define_clauses(definitions[0])
        optimizer.optimize_define_clauses(definitions[1])
        first_key = optimizer._create_define_cache_key(definitions[0])
        second_key = optimizer._create_define_cache_key(definitions[1])

        assert isinstance(first_key, tuple)
        assert list(optimizer.optimization_cache) == [
            first_key,
            second_key,
        ]

        # A hit makes the first plan most recent; admitting a third plan must
        # evict the second one and never exceed the configured capacity.
        optimizer.optimize_define_clauses(definitions[0])
        optimizer.optimize_define_clauses(definitions[2])
        third_key = optimizer._create_define_cache_key(definitions[2])

        assert list(optimizer.optimization_cache) == [
            first_key,
            third_key,
        ]

class TestDataGenerator:
    """Utility class for generating test data for aggregation testing."""
    
    @staticmethod
    def create_simple_numeric_data(size: int = 10) -> pd.DataFrame:
        """Create simple numeric data for basic aggregation testing."""
        return pd.DataFrame({
            'id': range(1, size + 1),
            'value': range(10, 10 + size * 10, 10)  # 10, 20, 30, ...
        })
    
    @staticmethod
    def create_financial_data(size: int = 20) -> pd.DataFrame:
        """Create financial-like data for testing."""
        np.random.seed(42)
        base_price = 100
        prices = [base_price]
        
        for _ in range(size - 1):
            change = np.random.normal(0, 2)
            new_price = max(prices[-1] + change, 10)  # Minimum price of 10
            prices.append(new_price)
        
        return pd.DataFrame({
            'day': pd.date_range('2024-01-01', periods=size),
            'price': prices,
            'volume': np.random.randint(100, 1000, size)
        })
    
    @staticmethod
    def create_sensor_data(size: int = 15) -> pd.DataFrame:
        """Create sensor-like data for testing."""
        np.random.seed(42)
        
        return pd.DataFrame({
            'id': range(1, size + 1),
            'sensor_id': [1] * size,
            'timestamp': pd.date_range('2024-01-01', periods=size, freq='h'),
            'value': np.random.uniform(10, 100, size),
            'confidence': np.random.uniform(0.7, 0.95, size)
        })
    
    @staticmethod
    def create_categorical_data(size: int = 10) -> pd.DataFrame:
        """Create data with categorical variables for testing."""
        np.random.seed(42)
        
        return pd.DataFrame({
            'id': range(1, size + 1),
            'label': np.random.choice(['A', 'B', 'C'], size),
            'value': np.random.randint(10, 100, size),
            'weight': np.random.uniform(1.0, 5.0, size)
        })
    
    @staticmethod
    def create_null_data(size: int = 10) -> pd.DataFrame:
        """Create data with NULL values for testing NULL handling."""
        np.random.seed(42)
        
        values = [10, None, 30, None, 50] * (size // 5 + 1)
        return pd.DataFrame({
            'id': range(1, size + 1),
            'value': values[:size]
        })

class TestValidator:
    """Utility class for validating test results."""
    
    @staticmethod
    def validate_dataframe_structure(df: pd.DataFrame, expected_columns: List[str]) -> bool:
        """Validate that DataFrame has expected structure."""
        if df.empty:
            logger.warning("DataFrame is empty")
            return False
        
        missing_columns = set(expected_columns) - set(df.columns)
        if missing_columns:
            logger.error(f"Missing columns: {missing_columns}")
            return False
        
        return True
    
    @staticmethod
    def validate_aggregation_results(df: pd.DataFrame, 
                                   aggregation_type: str,
                                   expected_pattern: str = "increasing") -> bool:
        """Validate that aggregation results follow expected patterns."""
        if df.empty:
            return False
        
        if aggregation_type == "running_sum" and expected_pattern == "increasing":
            # Running sums should generally be non-decreasing
            running_sum_col = None
            for col in df.columns:
                if 'sum' in col.lower():
                    running_sum_col = col
                    break
            
            if running_sum_col and not df[running_sum_col].isna().all():
                values = df[running_sum_col].dropna()
                is_increasing = all(values.iloc[i] <= values.iloc[i+1] 
                                  for i in range(len(values)-1))
                if not is_increasing:
                    logger.warning(f"Running sum is not increasing: {values.tolist()}")
                return is_increasing
        
        return True
    
    @staticmethod
    def compare_results_tolerance(actual: pd.DataFrame, 
                                expected: pd.DataFrame,
                                tolerance: float = 1e-6) -> bool:
        """Compare results with floating point tolerance."""
        try:
            pd.testing.assert_frame_equal(actual, expected, rtol=tolerance, atol=tolerance)
            return True
        except AssertionError as e:
            logger.error(f"DataFrames not equal within tolerance {tolerance}: {e}")
            return False

def setup_test_environment():
    """Setup the test environment with necessary configurations."""
    # Set pandas options for better test output
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 50)
    
    # Configure numpy for reproducible results
    np.random.seed(42)
    
    logger.info("Test environment configured")

def create_mock_aggregation_functions():
    """Create mock implementations of common aggregation functions."""
    
    def mock_stddev(values):
        """Mock standard deviation calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v)]
        if len(clean_values) < 2:
            return None
        return np.std(clean_values, ddof=1)
    
    def mock_variance(values):
        """Mock variance calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v)]
        if len(clean_values) < 2:
            return None
        return np.var(clean_values, ddof=1)
    
    def mock_geometric_mean(values):
        """Mock geometric mean calculation."""
        clean_values = [v for v in values if v is not None and not pd.isna(v) and v > 0]
        if not clean_values:
            return None
        return np.exp(np.mean(np.log(clean_values)))
    
    return {
        'stddev': mock_stddev,
        'variance': mock_variance,
        'geometric_mean': mock_geometric_mean
    }

# Create global instances
mock_match_recognize = MockMatchRecognize()
test_data_generator = TestDataGenerator()
test_validator = TestValidator()

# Export main functions
__all__ = [
    'MockMatchRecognize',
    'TestDataGenerator', 
    'TestValidator',
    'mock_match_recognize',
    'test_data_generator',
    'test_validator',
    'setup_test_environment',
    'create_mock_aggregation_functions'
]


def _resource_profile(memory_gib: float, cpus: int):
    memory_bytes = int(memory_gib * 1024 ** 3)
    return AdaptiveResourceProfile(
        memory=EffectiveMemorySnapshot(
            host_total_bytes=memory_bytes,
            host_available_bytes=memory_bytes,
            effective_limit_bytes=memory_bytes,
            effective_available_bytes=memory_bytes,
        ),
        cpu=EffectiveCPUSnapshot(
            host_logical_cpus=cpus,
            affinity_cpus=cpus,
            effective_cpus=cpus,
        ),
    )


class TestAdaptiveResourceProfile:
    def test_cpu_probe_intersects_host_affinity_and_cgroup_quota(self):
        files = {
            '/proc/self/cgroup': '0::/test',
            '/sys/fs/cgroup/test/cpu.max': '250000 100000',
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemResourceProbe(
            host_memory_provider=lambda: SimpleNamespace(
                total=64 * 1024 ** 3,
                available=48 * 1024 ** 3,
            ),
            host_cpu_provider=lambda: 64,
            affinity_provider=lambda: set(range(8)),
            text_reader=read_text,
        )

        cpu = probe.cpu_snapshot()

        assert cpu.host_logical_cpus == 64
        assert cpu.affinity_cpus == 8
        assert cpu.cgroup_quota_cpus == pytest.approx(2.5)
        assert cpu.effective_cpus == 2
        assert cpu.source == 'host+affinity+cgroup'

    def test_cgroup_v2_mount_root_is_resolved_from_mountinfo(self):
        gib = 1024 ** 3
        files = {
            '/proc/self/cgroup': '0::/tenant.slice/job.scope',
            '/proc/self/mountinfo': (
                '29 23 0:26 /tenant.slice /run/private-cgroup '
                'rw,nosuid,nodev,noexec,relatime - '
                'cgroup2 cgroup rw'
            ),
            '/run/private-cgroup/job.scope/memory.max': str(2 * gib),
            '/run/private-cgroup/job.scope/memory.current': str(gib // 2),
            '/run/private-cgroup/job.scope/cpu.max': '150000 100000',
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemResourceProbe(
            host_memory_provider=lambda: SimpleNamespace(
                total=64 * gib,
                available=48 * gib,
            ),
            host_cpu_provider=lambda: 64,
            affinity_provider=lambda: set(range(8)),
            text_reader=read_text,
        )

        memory = probe.memory_snapshot()
        cpu = probe.cpu_snapshot()

        assert memory.cgroup_limit_bytes == 2 * gib
        assert memory.cgroup_remaining_bytes == 3 * gib // 2
        assert memory.effective_limit_bytes == 2 * gib
        assert memory.effective_available_bytes == 3 * gib // 2
        assert cpu.cgroup_quota_cpus == pytest.approx(1.5)
        assert cpu.effective_cpus == 1

    def test_cgroup_v1_custom_mounts_are_resolved_from_mountinfo(self):
        gib = 1024 ** 3
        files = {
            '/proc/self/cgroup': (
                '5:memory:/docker/root/task\n'
                '4:cpu,cpuacct:/docker/root/task'
            ),
            '/proc/self/mountinfo': (
                '31 23 0:27 /docker/root /custom/memory rw - '
                'cgroup cgroup rw,memory\n'
                '32 23 0:28 /docker/root /custom/cpu rw - '
                'cgroup cgroup rw,cpu,cpuacct'
            ),
            (
                '/custom/memory/task/memory.limit_in_bytes'
            ): str(4 * gib),
            (
                '/custom/memory/task/memory.usage_in_bytes'
            ): str(gib),
            '/custom/cpu/task/cpu.cfs_quota_us': '250000',
            '/custom/cpu/task/cpu.cfs_period_us': '100000',
        }

        def read_text(path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        probe = SystemResourceProbe(
            host_memory_provider=lambda: SimpleNamespace(
                total=64 * gib,
                available=48 * gib,
            ),
            host_cpu_provider=lambda: 64,
            affinity_provider=lambda: set(range(16)),
            text_reader=read_text,
        )

        memory = probe.memory_snapshot()
        cpu = probe.cpu_snapshot()

        assert memory.cgroup_limit_bytes == 4 * gib
        assert memory.cgroup_remaining_bytes == 3 * gib
        assert cpu.cgroup_quota_cpus == pytest.approx(2.5)
        assert cpu.effective_cpus == 2

    def test_budgets_scale_down_and_saturate_at_stable_defaults(self):
        small = _resource_profile(0.5, 1)
        medium = _resource_profile(8, 4)
        large = _resource_profile(64, 16)
        very_large = _resource_profile(1024, 64)

        assert (
            small.query_budget_bytes
            < medium.query_budget_bytes
            < large.query_budget_bytes
        )
        assert large.query_budget_bytes == very_large.query_budget_bytes
        assert (
            small.cache_budget_bytes
            < medium.cache_budget_bytes
            < large.cache_budget_bytes
        )
        assert large.cache_budget_bytes == very_large.cache_budget_bytes

    def test_optional_cache_ceiling_remains_an_administrator_limit(self):
        gib = 1024 ** 3
        base = _resource_profile(1024, 64)
        unconstrained = AdaptiveResourceProfile(
            memory=base.memory,
            cpu=base.cpu,
            cache_hard_max_bytes=None,
        )
        constrained = AdaptiveResourceProfile(
            memory=unconstrained.memory,
            cpu=unconstrained.cpu,
            cache_hard_max_bytes=4 * gib,
        )

        assert unconstrained.cache_budget_bytes > 4 * gib
        assert constrained.cache_budget_bytes == 4 * gib

    def test_budget_ceilings_and_cache_entries_do_not_overcommit(self):
        gib = 1024 ** 3
        profile = AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=gib,
                host_available_bytes=gib,
                effective_limit_bytes=gib,
                effective_available_bytes=gib,
            ),
            cpu=EffectiveCPUSnapshot(
                host_logical_cpus=16,
                affinity_cpus=16,
                effective_cpus=16,
            ),
            cache_hard_max_bytes=32 * 1024 ** 2,
            query_hard_max_bytes=64 * 1024 ** 2,
            worker_hard_max=2,
        )

        assert profile.cache_budget_bytes == 32 * 1024 ** 2
        assert profile.query_budget_bytes == 64 * 1024 ** 2
        assert (
            profile.cache_budget_bytes + profile.query_budget_bytes
            <= profile.usable_available_bytes
        )
        assert profile.worker_count(
            requested=12,
            estimated_bytes_per_worker=16 * 1024 ** 2,
        ) == 2

        # The preferred minimum is not allowed to invent even one
        # four-megabyte entry when the component share cannot afford it.
        assert profile.cache_entry_limit(
            4 * 1024 ** 2,
            budget_share=0.01,
            minimum=32,
        ) == 0

    def test_derived_budgets_are_cached_without_changing_profile_semantics(
        self,
    ):
        import pickle

        profile = _resource_profile(8, 4)
        equivalent = _resource_profile(8, 4)

        expected = profile.as_dict()

        assert {
            'reserved_headroom_bytes',
            'usable_available_bytes',
            'cache_budget_bytes',
            'query_budget_bytes',
        } <= profile.__dict__.keys()
        assert profile.as_dict() == expected
        assert profile == equivalent
        assert hash(profile) == hash(equivalent)
        restored = pickle.loads(pickle.dumps(profile))
        assert restored == profile
        assert restored.as_dict() == expected

    def test_cache_entry_limit_cache_is_bounded_and_thread_safe(self):
        from concurrent.futures import ThreadPoolExecutor

        from src.utils import resource_profile

        cached_limit = resource_profile._cached_cache_entry_limit
        cached_limit.cache_clear()
        profile = _resource_profile(8, 4)
        arguments = [
            (
                entry_size_mib * 1024 ** 2,
                (entry_size_mib % 10 + 1) / 10.0,
            )
            for entry_size_mib in range(1, 700)
        ]

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda values: profile.cache_entry_limit(
                    values[0],
                    budget_share=values[1],
                    minimum=1,
                    maximum=500_000,
                ),
                arguments,
            ))

        assert results == [
            min(
                50_000,
                int(profile.cache_budget_bytes * budget_share)
                // entry_bytes,
            )
            for entry_bytes, budget_share in arguments
        ]
        cache_info = cached_limit.cache_info()
        assert cache_info.maxsize == 512
        assert cache_info.currsize <= cache_info.maxsize

        assert profile.cache_entry_limit(
            699 * 1024 ** 2,
            budget_share=1.0,
            minimum=1,
            maximum=500_000,
        ) == results[-1]
        before_hit = cached_limit.cache_info().hits
        assert profile.cache_entry_limit(
            699 * 1024 ** 2,
            budget_share=1.0,
            minimum=1,
            maximum=500_000,
        ) == results[-1]
        assert cached_limit.cache_info().hits == before_hit + 1

        with pytest.raises(
            ValueError,
            match='estimated_entry_bytes',
        ):
            profile.cache_entry_limit(0)
        with pytest.raises(ValueError, match='budget_share'):
            profile.cache_entry_limit(1, budget_share=0.0)
        with pytest.raises(ValueError, match='bounds'):
            profile.cache_entry_limit(1, minimum=2, maximum=1)

    def test_tiny_optional_cache_budget_disables_cache_without_expansion(
        self,
        monkeypatch,
    ):
        from src.config.production_config import MatchRecognizeConfig

        tiny_bytes = 64 * 1024
        profile = AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=tiny_bytes,
                host_available_bytes=tiny_bytes,
                effective_limit_bytes=tiny_bytes,
                effective_available_bytes=tiny_bytes,
            ),
            cpu=EffectiveCPUSnapshot(
                host_logical_cpus=2,
                affinity_cpus=2,
                effective_cpus=2,
            ),
        )
        monkeypatch.delenv('MR_ENABLE_CACHING', raising=False)

        config = MatchRecognizeConfig.from_env(profile)

        assert 0 < profile.cache_budget_bytes < 1024 ** 2
        assert profile.cache_entry_limit(64 * 1024) == 0
        assert config.performance.cache_memory_limit_mb == 0
        assert config.performance.cache_clear_threshold_mb == 0
        assert config.performance.cache_size_limit == 0
        assert config.performance.enable_caching is False

    def test_zero_is_a_valid_explicit_optional_cache_ceiling(self):
        from src.utils.performance_optimizer import SmartCacheConfig

        base = _resource_profile(8, 4)
        profile = AdaptiveResourceProfile(
            memory=base.memory,
            cpu=base.cpu,
            cache_hard_max_bytes=0,
            cache_entry_hard_max=0,
        )
        config = SmartCacheConfig.adaptive(profile)

        assert profile.cache_budget_bytes == 0
        assert profile.cache_entry_limit(1) == 0
        assert config.max_entries == 0

    def test_existing_smart_cache_rebinds_to_changed_environment(self):
        from src.utils.performance_optimizer import SmartCache

        large = _resource_profile(8, 4)
        disabled = AdaptiveResourceProfile(
            memory=large.memory,
            cpu=large.cpu,
            cache_hard_max_bytes=0,
            cache_entry_hard_max=0,
        )
        cache = SmartCache(resource_profile=large)
        assert cache.put("compiled", {"value": 1}, size_hint=0.001)
        assert cache.get_statistics()['entries_count'] == 1

        cache.apply_resource_profile(disabled)

        assert cache.config.max_size_mb == 0
        assert cache.config.max_entries == 0
        assert cache.get_statistics()['entries_count'] == 0
        assert cache.put("new", {"value": 2}, size_hint=0.001) is False

    def test_zero_query_capacity_fails_before_execution(self):
        profile = AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=1024,
                host_available_bytes=0,
                effective_limit_bytes=1024,
                effective_available_bytes=0,
            ),
            cpu=EffectiveCPUSnapshot(
                host_logical_cpus=1,
                affinity_cpus=1,
                effective_cpus=1,
            ),
        )

        assert profile.query_budget_bytes == 0
        with pytest.raises(InsufficientExecutionResourcesError):
            profile.require_query_capacity()

    def test_concurrent_query_count_reserves_the_shared_cache_pool(
        self,
        monkeypatch,
    ):
        from src.config.production_config import MatchRecognizeConfig

        profile = _resource_profile(1, 16)
        for variable in (
            'MR_MAX_CONCURRENT_QUERIES',
            'MR_QUERY_QUEUE_SIZE',
            'MR_MAX_MEMORY_MB',
            'MR_CACHE_MEMORY_LIMIT_MB',
            'MR_CACHE_SIZE_LIMIT',
        ):
            monkeypatch.delenv(variable, raising=False)

        config = MatchRecognizeConfig.from_env(profile)
        concurrent_queries = config.resources.max_concurrent_queries

        assert concurrent_queries == 1
        assert (
            concurrent_queries * profile.query_budget_bytes
            + profile.cache_budget_bytes
            <= profile.usable_available_bytes
        )

    def test_worker_count_is_bounded_by_cpu_memory_and_request(self):
        profile = _resource_profile(1, 16)

        assert profile.worker_count(
            requested=12,
            estimated_bytes_per_worker=512 * 1024 ** 2,
        ) == 1
        assert profile.worker_count(
            requested=3,
            estimated_bytes_per_worker=32 * 1024 ** 2,
        ) == 3

    def test_production_defaults_follow_injected_resource_profile(
        self,
        monkeypatch,
    ):
        from src.config.production_config import MatchRecognizeConfig

        for variable in (
            'MR_MAX_MEMORY_MB',
            'MR_CACHE_MEMORY_LIMIT_MB',
            'MR_CACHE_SIZE_LIMIT',
            'MR_MAX_WORKERS',
        ):
            monkeypatch.delenv(variable, raising=False)

        small = MatchRecognizeConfig.from_env(_resource_profile(1, 1))
        large = MatchRecognizeConfig.from_env(_resource_profile(64, 16))

        assert (
            small.performance.max_memory_mb
            < large.performance.max_memory_mb
        )
        assert (
            small.performance.cache_memory_limit_mb
            < large.performance.cache_memory_limit_mb
        )
        assert (
            small.performance.cache_size_limit
            < large.performance.cache_size_limit
        )
        assert small.performance.max_workers == 1
        assert large.performance.max_workers == 4

    def test_environment_resource_values_are_ceilings_not_expansions(
        self,
        monkeypatch,
    ):
        from src.config.production_config import MatchRecognizeConfig

        profile = _resource_profile(1, 2)
        monkeypatch.setenv('MR_MAX_MEMORY_MB', '999999')
        monkeypatch.setenv('MR_CACHE_MEMORY_LIMIT_MB', '999999')
        monkeypatch.setenv('MR_CACHE_SIZE_LIMIT', '999999')
        monkeypatch.setenv('MR_MAX_WORKERS', '999999')

        config = MatchRecognizeConfig.from_env(profile)

        assert config.performance.max_memory_mb <= (
            profile.query_budget_bytes // 1024 ** 2
        )
        assert config.performance.cache_memory_limit_mb <= (
            profile.cache_budget_bytes // 1024 ** 2
        )
        assert config.performance.cache_size_limit <= (
            profile.cache_entry_limit(
                estimated_entry_bytes=64 * 1024,
                budget_share=1.0,
                minimum=128,
                maximum=500_000,
            )
        )
        assert config.performance.max_workers <= profile.cpu.effective_cpus

    def test_environment_ceilings_are_shared_by_all_profile_consumers(
        self,
        monkeypatch,
    ):
        mib = 1024 ** 2
        monkeypatch.setenv('MR_MAX_MEMORY_MB', '128')
        monkeypatch.setenv('MR_CACHE_MEMORY_LIMIT_MB', '64')
        monkeypatch.setenv('MR_CACHE_SIZE_LIMIT', '7')
        monkeypatch.setenv('MR_MAX_WORKERS', '2')

        profile = _resource_profile(64, 16).with_environment_ceilings()

        assert profile.query_budget_bytes == 128 * mib
        assert profile.cache_budget_bytes == 64 * mib
        # The administrator allows at most two workers, while the 128-MiB
        # query ceiling can afford only one 256-MiB-estimated worker.
        assert profile.worker_count() == 1
        assert profile.cache_entry_limit(
            estimated_entry_bytes=1,
            budget_share=1.0,
            minimum=1,
            maximum=500_000,
        ) == 7
        from src.utils.performance_optimizer import SmartCacheConfig

        cache_config = SmartCacheConfig.adaptive(profile)
        assert cache_config.max_entries == 7
        assert (
            cache_config.l1_max_entries
            + cache_config.l2_max_entries
            + cache_config.l3_max_entries
            == 7
        )

    def test_invalid_shared_environment_ceiling_fails_explicitly(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv('MR_MAX_WORKERS', '0')

        with pytest.raises(ValueError, match='MR_MAX_WORKERS'):
            _resource_profile(8, 8).with_environment_ceilings()

    def test_environment_can_disable_optional_cache_capacity(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv('MR_CACHE_MEMORY_LIMIT_MB', '0')
        monkeypatch.setenv('MR_CACHE_SIZE_LIMIT', '0')

        profile = _resource_profile(8, 4).with_environment_ceilings()

        assert profile.cache_budget_bytes == 0
        assert profile.cache_entry_limit(1) == 0

    def test_memory_pressure_uses_effective_not_host_memory(
        self,
        monkeypatch,
    ):
        from src.utils import memory_management

        profile = _resource_profile(2, 2)
        constrained_memory = EffectiveMemorySnapshot(
            host_total_bytes=64 * 1024 ** 3,
            host_available_bytes=48 * 1024 ** 3,
            cgroup_limit_bytes=2 * 1024 ** 3,
            cgroup_remaining_bytes=100 * 1024 ** 2,
            effective_limit_bytes=2 * 1024 ** 3,
            effective_available_bytes=100 * 1024 ** 2,
            source='host+cgroup',
        )
        constrained = AdaptiveResourceProfile(
            memory=constrained_memory,
            cpu=profile.cpu,
        )
        monkeypatch.setattr(
            memory_management,
            'get_adaptive_resource_profile',
            lambda **kwargs: constrained,
        )

        pressure = (
            memory_management.AdaptivePoolManager()
            .get_memory_pressure()
        )

        assert pressure.pressure_level == 'critical'
        assert pressure.memory_percent > 95

    def test_smart_cache_levels_share_one_adaptive_byte_budget(self):
        from src.utils.performance_optimizer import SmartCacheConfig

        profile = _resource_profile(8, 4)
        config = SmartCacheConfig.adaptive(profile)

        level_total = (
            config.l1_cache_size_mb
            + config.l2_cache_size_mb
            + config.l3_cache_size_mb
        )
        assert level_total == pytest.approx(config.max_size_mb)
        assert config.max_entries == (
            config.l1_max_entries
            + config.l2_max_entries
            + config.l3_max_entries
        )

    def test_smart_cache_with_unaffordable_entries_stays_disabled(self):
        from src.utils.performance_optimizer import SmartCache, SmartCacheConfig

        tiny_bytes = 64 * 1024
        profile = AdaptiveResourceProfile(
            memory=EffectiveMemorySnapshot(
                host_total_bytes=tiny_bytes,
                host_available_bytes=tiny_bytes,
                effective_limit_bytes=tiny_bytes,
                effective_available_bytes=tiny_bytes,
            ),
            cpu=EffectiveCPUSnapshot(1, 1, 1),
        )
        config = SmartCacheConfig.adaptive(profile)
        cache = SmartCache(config)
        cache._check_memory_pressure = lambda: False

        assert config.max_size_mb == pytest.approx(
            profile.cache_budget_bytes / 1024 ** 2
        )
        assert config.max_entries == 0
        assert config.max_predictive_entries == 0
        assert cache.put("small", b"x") is False
        assert cache.get_statistics()["entries_count"] == 0

    def test_smart_cache_rejects_oversized_first_entry(self):
        from src.utils.performance_optimizer import SmartCache, SmartCacheConfig

        config = SmartCacheConfig(
            max_size_mb=0.001,
            max_entries=10,
            enable_background_optimization=False,
        )
        cache = SmartCache(config)
        cache._check_memory_pressure = lambda: False

        assert cache.put("oversized", b"x", size_hint=1.0) is False
        assert cache.get("oversized") is None
        assert cache.get_statistics()["entries_count"] == 0

    def test_smart_cache_pressure_never_increases_adaptive_ceiling(self):
        from src.utils.performance_optimizer import SmartCache, SmartCacheConfig

        config = SmartCacheConfig(
            max_size_mb=0.001,
            max_entries=1,
            enable_background_optimization=False,
        )
        cache = SmartCache(config)

        original_size = config.max_size_mb
        original_entries = config.max_entries
        cache._adaptive_resize()

        assert 0 <= config.max_size_mb <= original_size
        assert 0 <= config.max_entries <= original_entries

    def test_smart_cache_eviction_releases_keyed_analysis_metadata(self):
        from src.utils.performance_optimizer import (
            CacheEvictionPolicy,
            SmartCache,
            SmartCacheConfig,
        )

        config = SmartCacheConfig(
            max_size_mb=1.0,
            max_entries=2,
            eviction_policy=CacheEvictionPolicy.LRU,
            enable_background_optimization=False,
            enable_dynamic_sizing=False,
            enable_predictive_loading=False,
        )
        cache = SmartCache(config)
        cache._check_memory_pressure = lambda: False

        for index in range(10):
            key = f"pattern-{index}"
            assert cache.put(key, index, size_hint=0.001)
            assert cache.get(key) == index

        retained = set(cache.l1_cache) | set(cache.l2_cache) | set(cache.l3_cache)
        assert len(retained) <= config.max_entries
        assert set(cache.access_patterns) <= retained
        assert set(cache.frequency_counter) <= retained
        assert cache.hot_patterns <= retained
        assert cache.navigation_patterns <= retained
        assert set(cache.pattern_vectors) <= retained
        assert set(cache.similarity_cache) <= retained

    def test_pattern_stage_cache_admission_uses_graph_size_hint(
        self,
        monkeypatch,
    ):
        from src.utils import pattern_cache

        observed = {}

        class RecordingCache:
            def put(self, key, value, size_hint=None, metadata=None):
                observed.update(
                    key=key,
                    value=value,
                    size_hint=size_hint,
                    metadata=metadata,
                )
                return True

        states = [
            SimpleNamespace(transitions=[SimpleNamespace()]),
            SimpleNamespace(transitions=[]),
        ]
        nfa = SimpleNamespace(states=states)
        monkeypatch.setattr(
            pattern_cache,
            "get_pattern_cache",
            lambda: RecordingCache(),
        )

        assert pattern_cache.cache_pattern(
            "compiled-pattern",
            None,
            nfa,
            compilation_time=0.25,
        )
        assert observed["value"] == (None, nfa, 0.25)
        assert observed["size_hint"] >= (2 * 16 + 4) / 1024

    def test_automata_cache_options_are_semantic_and_subset_aware(self):
        from src.executor.match_recognize import _automata_compilation_options

        first = _automata_compilation_options(
            {"U": ["B", "A"], "V": ["C"]}
        )
        reordered = _automata_compilation_options(
            {"V": ["C"], "U": ["A", "B"]}
        )
        different = _automata_compilation_options(
            {"U": ["A"], "V": ["C"]}
        )

        assert first == reordered
        assert first != different
        assert set(first) == {
            "automata_compiler_schema",
            "nfa_compiler_schema",
            "subsets",
        }


class TestParallelExecutionFailClosed:
    """Resource exhaustion and worker errors are never empty matches."""

    @staticmethod
    def _work_item(partition_id="partition_0"):
        from src.utils.performance_optimizer import ParallelWorkItem

        return ParallelWorkItem(
            partition_id=partition_id,
            data_subset=[{"value": 1}],
            pattern="A",
            config={},
        )

    def test_thread_timeout_raises_typed_error(self):
        import time

        from src.utils.performance_optimizer import (
            ParallelExecutionConfig,
            ParallelExecutionManager,
            ParallelExecutionTimeoutError,
        )

        manager = ParallelExecutionManager(
            ParallelExecutionConfig(
                max_workers=1,
                min_data_size_for_parallel=0,
                thread_timeout_seconds=0.01,
            )
        )

        def slow_result(item):
            time.sleep(0.05)
            return {"matches": [{"start": 0, "end": 0}]}

        manager._execute_work_item = slow_result
        manager._check_resource_availability = lambda: True
        manager.resource_monitor.start_monitoring = lambda: None
        manager.resource_monitor.stop_monitoring = lambda: None

        with pytest.raises(ParallelExecutionTimeoutError) as error:
            manager.execute_parallel_patterns([
                self._work_item("partition_0"),
                self._work_item("partition_1"),
            ])

        assert error.value.partition_id == "partition_0"
        assert error.value.execution_mode == "thread"
        assert error.value.timeout_seconds == pytest.approx(0.01)

    def test_worker_exception_is_not_returned_as_empty_matches(self):
        from src.utils.performance_optimizer import (
            ParallelExecutionConfig,
            ParallelExecutionManager,
            ParallelWorkItemExecutionError,
        )

        manager = ParallelExecutionManager(
            ParallelExecutionConfig(max_workers=1)
        )

        def fail(item):
            raise ValueError("forced worker failure")

        manager._execute_work_item = fail

        with pytest.raises(ParallelWorkItemExecutionError) as error:
            manager._execute_sequential([self._work_item()])

        assert isinstance(error.value.__cause__, ValueError)
        assert "forced worker failure" in str(error.value)

    def test_process_timeout_raises_typed_error(self):
        import concurrent.futures

        from src.utils.performance_optimizer import (
            ParallelExecutionConfig,
            ParallelExecutionManager,
            ParallelExecutionTimeoutError,
        )

        observed = {}

        class TimeoutFuture:
            def result(self, timeout=None):
                observed["timeout"] = timeout
                raise concurrent.futures.TimeoutError()

            def cancel(self):
                observed["cancelled"] = True
                return True

        class FakeProcessPool:
            def submit(self, function, item):
                return TimeoutFuture()

            def shutdown(self, **kwargs):
                observed["shutdown"] = kwargs

        manager = ParallelExecutionManager(
            ParallelExecutionConfig(
                max_workers=1,
                process_timeout_seconds=0.02,
            )
        )
        manager.process_pool = FakeProcessPool()

        with pytest.raises(ParallelExecutionTimeoutError) as error:
            manager._execute_with_processes([self._work_item()])

        assert error.value.execution_mode == "process"
        assert observed["timeout"] == pytest.approx(0.02)
        assert observed["cancelled"] is True
        assert observed["shutdown"] == {
            "wait": False,
            "cancel_futures": True,
        }

    def test_executor_shutdown_supports_python_38_signature(self):
        from src.utils.performance_optimizer import (
            _shutdown_executor_compat,
        )

        observed = []

        class LegacyExecutor:
            def shutdown(self, wait=True, **kwargs):
                observed.append((wait, kwargs))
                if "cancel_futures" in kwargs:
                    raise TypeError("unexpected keyword argument")

        _shutdown_executor_compat(LegacyExecutor())

        assert observed == [
            (False, {"cancel_futures": True}),
            (False, {}),
        ]

    def test_uninstalled_generic_executor_fails_explicitly(self):
        from src.utils.performance_optimizer import (
            ParallelExecutionConfig,
            ParallelExecutionManager,
            ParallelExecutionUnavailableError,
        )

        manager = ParallelExecutionManager(
            ParallelExecutionConfig(max_workers=1)
        )

        with pytest.raises(ParallelExecutionUnavailableError):
            manager._execute_sequential([self._work_item()])
