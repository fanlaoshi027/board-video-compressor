import unittest

from compress import _cut_filter


class CutFilterTests(unittest.TestCase):
    def test_single_cut_keeps_both_sides(self):
        graph = _cut_filter([(10, 20)], 60, has_audio=False)
        self.assertIn("trim=start=0.000:end=10.000", graph)
        self.assertIn("trim=start=20.000:end=60.000", graph)
        self.assertIn("concat=n=2:v=1:a=0", graph)

    def test_overlapping_cuts_are_merged(self):
        graph = _cut_filter([(10, 20), (15, 30)], 60, has_audio=False)
        self.assertNotIn("end=15.000", graph)
        self.assertIn("trim=start=0.000:end=10.000", graph)
        self.assertIn("trim=start=30.000:end=60.000", graph)
        self.assertIn("concat=n=2:v=1:a=0", graph)

    def test_cut_at_beginning(self):
        graph = _cut_filter([(0, 8)], 60, has_audio=False)
        self.assertNotIn("start=0.000:end=8.000", graph)
        self.assertIn("trim=start=8.000:end=60.000", graph)

    def test_cut_at_end(self):
        graph = _cut_filter([(50, 60)], 60, has_audio=False)
        self.assertIn("trim=start=0.000:end=50.000", graph)
        self.assertNotIn("end=60.000", graph.split("[v0]")[-1])

    def test_audio_is_concatenated_with_video(self):
        graph = _cut_filter([(10, 20)], 60, has_audio=True)
        self.assertIn("atrim=start=10.000:end=20.000", graph)
        self.assertIn("concat=n=2:v=1:a=1[outv][outa]", graph)

    def test_all_video_deleted_raises(self):
        with self.assertRaises(ValueError):
            _cut_filter([(0, 60)], 60, has_audio=False)


if __name__ == "__main__":
    unittest.main()
