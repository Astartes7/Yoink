from yoink.core.models import DownloadJob, JobStatus


def test_job_snapshot_and_cancel():
    job = DownloadJob("https://example.com", "out")
    job.update(title="Example", percent=42, status=JobStatus.DOWNLOADING)
    snapshot = job.snapshot()
    assert snapshot["title"] == "Example"
    assert snapshot["percent"] == 42
    job.cancel()
    assert job.cancel_requested.is_set()
