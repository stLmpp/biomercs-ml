from pathlib import Path
from unittest.mock import MagicMock, patch

from biomercs_ml import downloader


@patch("biomercs_ml.downloader.yt_dlp.YoutubeDL")
def test_download_requests_best_quality_and_mp4_output(mock_ydl_class, tmp_path):
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = {"id": "abc123"}
    mock_ydl.prepare_filename.return_value = str(tmp_path / "abc123.mp4")
    mock_ydl_class.return_value = mock_ydl

    result = downloader.download("https://youtube.com/watch?v=abc123", tmp_path)

    called_opts = mock_ydl_class.call_args[0][0]
    assert called_opts["format"] == "bestvideo+bestaudio/best"
    assert called_opts["merge_output_format"] == "mp4"
    assert result == (tmp_path / "abc123.mp4")
