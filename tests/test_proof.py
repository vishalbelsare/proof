import os
import shutil
import unittest
from copy import deepcopy
from glob import glob

import proof

TEST_CACHE = '.proof-test'


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.executed_stage1 = 0
        self.data_before_stage1 = None
        self.data_after_stage1 = None

        self.executed_stage2 = 0
        self.data_before_stage2 = None
        self.data_after_stage2 = None

        self.executed_stage_unicode = 0

        self.executed_stage_never_cache = 0

    def tearDown(self):
        shutil.rmtree(TEST_CACHE)

    def stage1(self, data):
        self.executed_stage1 += 1
        self.data_before_stage1 = deepcopy(data)

        data['stage1'] = 5

        self.data_after_stage1 = deepcopy(data)

    def stage2(self, data):
        self.executed_stage2 += 1
        self.data_before_stage2 = deepcopy(data)

        data['stage2'] = data['stage1'] * 5

        self.data_after_stage2 = deepcopy(data)

    def stage_unicode(self, data):
        self.executed_stage_unicode += 1

        data['state_unicode'] = 'ßäœ'

    @proof.never_cache
    def stage_never_cache(self, data):
        self.executed_stage_never_cache += 1

    def stage_noop(self, data):
        pass

    def test_data_flow(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)

        data = {}

        analysis.run(data)

        self.assertEqual(data, {})
        self.assertEqual(self.data_before_stage1, {})
        self.assertEqual(self.data_after_stage1, {'stage1': 5})
        self.assertEqual(self.data_before_stage2, {'stage1': 5})
        self.assertEqual(self.data_after_stage2, {'stage1': 5, 'stage2': 25})

    def test_caching(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

    def test_cache_unicode(self):
        analysis = proof.Analysis(self.stage_unicode, cache_dir=TEST_CACHE)
        analysis.run()

        self.assertEqual(self.executed_stage_unicode, 1)

    def test_never_cache(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage_never_cache)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage_never_cache, 1)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage_never_cache, 2)

    def test_descendent_fingerprint_deleted(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        stage2_analysis = analysis.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

        os.remove(stage2_analysis._cache_path)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 2)

    def test_ancestor_fingerprint_deleted(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

        os.remove(analysis._cache_path)

        analysis.run()

        self.assertEqual(self.executed_stage1, 2)
        self.assertEqual(self.executed_stage2, 2)

    def test_cache_reused(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

        analysis2 = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis2.then(self.stage2)

        analysis2.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

    def test_ancestor_changed(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        noop = analysis.then(self.stage_noop)
        noop.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 1)

        analysis2 = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis2.then(self.stage2)

        analysis2.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 2)

    def test_same_function_twice_parallel(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        noop = analysis.then(self.stage_noop)
        noop.then(self.stage2)
        noop.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 2)

    def test_same_function_twice_sequence(self):
        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)
        analysis.then(self.stage_noop)
        analysis.then(self.stage2)

        analysis.run()

        self.assertEqual(self.executed_stage1, 1)
        self.assertEqual(self.executed_stage2, 2)

    def test_cleanup(self):
        self.assertFalse(os.path.exists(TEST_CACHE))

        analysis = proof.Analysis(self.stage1, cache_dir=TEST_CACHE)
        analysis.then(self.stage2)

        data = {}

        # Initial run, creates two cache files
        analysis.run(data)

        cache_files = glob(os.path.join(TEST_CACHE, '*.cache'))
        self.assertEqual(len(cache_files), 2)

        # Create false third cache file
        open(os.path.join(TEST_CACHE, 'foo.cache'), 'a').close()

        cache_files2 = glob(os.path.join(TEST_CACHE, '*.cache'))
        self.assertEqual(len(cache_files2), 3)

        # Second run, removes false cache file
        analysis.run(data)

        cache_files3 = glob(os.path.join(TEST_CACHE, '*.cache'))
        self.assertEqual(len(cache_files3), 2)
        self.assertSequenceEqual(cache_files, cache_files3)
