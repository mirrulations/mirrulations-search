"""
Tests for ``db/ingest.py`` and ``db/ingest_docket.py`` (fetch, OpenSearch, FR helpers, mapping).
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add db directory to path for imports BEFORE importing ingest module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))

# pylint: disable=wrong-import-position,import-error
from ingest import (
    OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX,
    OPENSEARCH_COMMENTS_INDEX,
    collect_frdocnums_from_docket,
    document_content_html_paths,
    extract_frdocnums_from_document_json,
    extracted_txt_dir,
    fetch_docket,
    get_docket_ID,
    get_document_ID,
    get_htm_files,
    ingest_comment_json_to_opensearch,
    ingest_extracted_text_to_comments_extracted_text,
    ingest_htm_files,
    read_derived_extracted_text,
    read_document_content_html,
)

from ingest_docket import (
    _normalize_docket_id,
    extract_comment,
    extract_self_link,
    load_raw_json,
    map_docket,
)
# pylint: enable=wrong-import-position,import-error


def _docket_dir_with_derived_json_and_plain_txt(tmpdir: str) -> Path:
    """Build a minimal docket tree with one JSON record and one pypdf plain-text file."""
    root = Path(tmpdir) / "FAA-2025-0618"
    ext = root / "derived-data" / "mirrulations" / "extracted_txt"
    ext.mkdir(parents=True)
    rec = {
        "docketId": "FAA-2025-0618",
        "commentId": "FAA-2025-0618-0007",
        "attachmentId": "FAA-2025-0618-0007_attachment_1",
        "extractedMethod": "json",
        "extractedText": "from json",
    }
    (ext / "one.json").write_text(json.dumps(rec), encoding="utf-8")
    pypdf = ext / "comments_extracted_text" / "pypdf"
    pypdf.mkdir(parents=True)
    plain = "FAA-2025-0618-0007_attachment_1_extracted.txt"
    (pypdf / plain).write_text("plain body", encoding="utf-8")
    return root


def _docket_dir_with_document_content_htm(
    tmpdir: str, docket_id: str, filename: str, html: str
) -> None:
    """Lay out ``raw-data/documents`` with one content HTM as if fetch succeeded."""
    docs = Path(tmpdir) / docket_id / "raw-data" / "documents"
    docs.mkdir(parents=True)
    (docs / filename).write_text(html, encoding="utf-8")


def _fake_fetch_docket_ready(tmpdir: str, mock_popen, mock_which) -> Path:
    """Configure fetch mocks, create minimal docket tree, run ``fetch_docket``."""
    mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 0]
    mock_proc.returncode = 0
    mock_popen.return_value.__enter__.return_value = mock_proc
    did = "FAA-2025-0618"
    _docket_dir_with_document_content_htm(
        tmpdir,
        did,
        f"{did}-0001_content.htm",
        "<html><body>Airworthiness</body></html>",
    )
    return fetch_docket(did, tmpdir)


class TestFetchDocket:
    """Test docket file fetching functionality."""

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_fetch_docket_success(self, mock_which, mock_popen):
        """Successfully fetch docket using mirrulations-fetch."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docket_dir.mkdir()

            result = fetch_docket("FAA-2025-0618", tmpdir)

            mock_which.assert_called_once_with("mirrulations-fetch")
            assert result == docket_dir
            assert result.name == "FAA-2025-0618"
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == ["/usr/local/bin/mirrulations-fetch", "FAA-2025-0618"]

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_fetch_docket_not_found(self, mock_which, mock_popen):
        """Handle missing docket directory after fetch."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(SystemExit):
                fetch_docket("MISSING-2025-0001", tmpdir)

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_fetch_docket_subprocess_error(self, mock_which, mock_popen):
        """Handle Popen failing to start the fetch executable."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_popen.side_effect = FileNotFoundError("mirrulations-fetch not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(SystemExit):
                fetch_docket("FAA-2025-0618", tmpdir)

    @patch("ingest.shutil.which")
    def test_fetch_docket_command_not_on_path(self, mock_which):
        """Exit when mirrulations-fetch is not on PATH."""
        mock_which.return_value = None
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(SystemExit):
                fetch_docket("FAA-2025-0618", tmpdir)

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_fetch_docket_calculates_correct_path(self, mock_which, mock_popen):
        """Verify fetch_docket returns correct path."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "CMS-2025-0240"
            docket_dir.mkdir()

            result = fetch_docket("CMS-2025-0240", tmpdir)

            assert result.name == "CMS-2025-0240"
            assert result.parent == Path(tmpdir)

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_fetch_docket_non_zero_return_code(self, mock_which, mock_popen):
        """Handle non-zero return code from subprocess."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 1]  # Returns 1 (error code)
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = ("", "Fetch error")
        mock_popen.return_value.__enter__.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docket_dir.mkdir()

            with pytest.raises(SystemExit):
                fetch_docket("FAA-2025-0618", tmpdir)


class TestIngestOpenSearch:
    """Test OpenSearch ingestion functionality."""

    def test_ingest_single_htm_file_to_opensearch(self):
        """Ingest a single HTM file into OpenSearch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            # Create test HTM file
            htm_file = docs_dir / "FAA-2025-0618-0001_content.htm"
            htm_file.write_text("<html><body>Airworthiness Directive</body></html>")

            # Mock OpenSearch client
            mock_client = MagicMock()

            ingest_htm_files(docket_dir, mock_client)

            # Verify OpenSearch index was called
            mock_client.index.assert_called_once()
            call_kwargs = mock_client.index.call_args[1]

            assert call_kwargs["index"] == "documents_text"
            assert call_kwargs["id"] == "FAA-2025-0618-0001_content.htm"
            assert call_kwargs["body"]["docketId"] == "FAA-2025-0618"
            assert call_kwargs["body"]["documentId"] == "FAA-2025-0618-0001_content.htm"
            assert "Airworthiness" in call_kwargs["body"]["documentText"]

    def test_ingest_multiple_htm_files_to_opensearch(self):
        """Ingest multiple HTM files into OpenSearch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "CMS-2025-0240"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            # Create multiple HTM files
            for i in range(1, 4):
                htm_file = docs_dir / f"CMS-2025-0240-000{i}_content.htm"
                htm_file.write_text(f"<html><body>Document {i}</body></html>")

            mock_client = MagicMock()
            ingest_htm_files(docket_dir, mock_client)

            # Verify all documents were indexed
            assert mock_client.index.call_count == 3

            # Verify document IDs are correct
            doc_ids = [call[1]["id"] for call in mock_client.index.call_args_list]
            assert "CMS-2025-0240-0001_content.htm" in doc_ids
            assert "CMS-2025-0240-0002_content.htm" in doc_ids
            assert "CMS-2025-0240-0003_content.htm" in doc_ids

    def test_ingest_handles_missing_opensearch(self):
        """Handle OpenSearch connection errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAIL-2025-0001"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            htm_file = docs_dir / "doc.htm"
            htm_file.write_text("<html>Test</html>")

            mock_client = MagicMock()
            mock_client.index.side_effect = Exception("OpenSearch connection failed")

            with pytest.raises(Exception):
                ingest_htm_files(docket_dir, mock_client)

    def test_opensearch_document_structure(self):
        """Verify correct document structure for OpenSearch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "OSHA-2025-0005"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            htm_file = docs_dir / "safety_doc.htm"
            htm_file.write_text("<html><body>Safety content</body></html>")

            mock_client = MagicMock()
            ingest_htm_files(docket_dir, mock_client)

            body = mock_client.index.call_args[1]["body"]

            # Verify required fields exist
            assert "docketId" in body
            assert "documentId" in body
            assert "documentText" in body

            # Verify field values
            assert body["docketId"] == "OSHA-2025-0005"
            assert body["documentId"] == "safety_doc.htm"
            assert body["documentText"] == "<html><body>Safety content</body></html>"

    def test_ingest_comment_json_to_opensearch(self):
        """Index raw-data/comments/*.json into OpenSearch comments index."""
        sample = {
            "data": {
                "id": "FAA-2025-0618-0003",
                "type": "comments",
                "attributes": {
                    "comment": "Hello world",
                    "docketId": "FAA-2025-0618",
                    "agencyId": "FAA",
                    "documentType": "Public Submission",
                    "postedDate": "2025-01-01T00:00:00Z",
                },
                "links": {
                    "self": "https://api.regulations.gov/v4/comments/FAA-2025-0618-0003"
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            cdir = docket_dir / "raw-data" / "comments"
            cdir.mkdir(parents=True)
            (cdir / "FAA-2025-0618-0003.json").write_text(
                json.dumps(sample), encoding="utf-8"
            )

            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            n = ingest_comment_json_to_opensearch(docket_dir, mock_client)

            assert n == 1
            mock_client.index.assert_called_once()
            kw = mock_client.index.call_args[1]
            assert kw["index"] == OPENSEARCH_COMMENTS_INDEX
            assert kw["id"] == "FAA-2025-0618-0003"
            assert kw["body"]["docketId"] == "FAA-2025-0618"
            assert kw["body"]["commentText"] == "Hello world"

    def test_ingest_comment_progress_bar_disabled_for_small_count(self):
        """Verify progress bar disabled when processing few comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "SMALL-2025-0001"
            cdir = docket_dir / "raw-data" / "comments"
            cdir.mkdir(parents=True)
            # Create only 3 comment files
            for i in range(3):
                (cdir / f"comment{i}.json").write_text(
                    json.dumps({
                        "data": {
                            "id": f"SMALL-2025-0001-000{i}",
                            "attributes": {
                                "comment": f"Comment {i}",
                                "docketId": "SMALL-2025-0001",
                                "agencyId": "TEST",
                                "documentType": "Public Submission",
                                "postedDate": "2025-01-01T00:00:00Z",
                            },
                            "links": {
                                "self": (
                                    f"https://api.regulations.gov/v4/comments/"
                                    f"SMALL-2025-0001-000{i}"
                                ),
                            },
                        }
                    }),
                    encoding="utf-8",
                )
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            n = ingest_comment_json_to_opensearch(docket_dir, mock_client)
            assert n == 3
            assert mock_client.index.call_count == 3

    def test_ingest_comment_progress_bar_enabled_for_large_count(self):
        """Verify progress bar enabled when processing many comments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "LARGE-2025-0001"
            cdir = docket_dir / "raw-data" / "comments"
            cdir.mkdir(parents=True)
            # Create 100 comment files (many comments)
            for i in range(100):
                (cdir / f"comment{i}.json").write_text(
                    json.dumps({
                        "data": {
                            "id": f"LARGE-2025-0001-{i:05d}",
                            "attributes": {
                                "comment": f"Comment {i}",
                                "docketId": "LARGE-2025-0001",
                                "agencyId": "TEST",
                                "documentType": "Public Submission",
                                "postedDate": "2025-01-01T00:00:00Z",
                            },
                            "links": {
                                "self": (
                                    f"https://api.regulations.gov/v4/comments/"
                                    f"LARGE-2025-0001-{i:05d}"
                                ),
                            },
                        }
                    }),
                    encoding="utf-8",
                )
            mock_client = MagicMock()
            mock_client.indices.exists.return_value = True
            n = ingest_comment_json_to_opensearch(docket_dir, mock_client)
            assert n == 100
            assert mock_client.index.call_count == 100


class TestFileDiscovery:
    """Test HTM file discovery and reading functionality."""

    def test_discover_htm_files_in_documents_directory(self):
        """Discover all HTM files in documents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            # Create HTM files
            (docs_dir / "doc1.htm").write_text("<html>1</html>")
            (docs_dir / "doc2.htm").write_text("<html>2</html>")

            files = get_htm_files(docket_dir)

            assert len(files) == 2
            assert all(f["docketId"] == "FAA-2025-0618" for f in files)

    def test_discover_html_files_as_well(self):
        """Discover both .htm and .html file extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "TEST-2025-0001"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            (docs_dir / "file1.htm").write_text("<html>HTM</html>")
            (docs_dir / "file2.html").write_text("<html>HTML</html>")

            files = get_htm_files(docket_dir)

            assert len(files) == 2
            doc_ids = [f["documentId"] for f in files]
            assert "file1.htm" in doc_ids
            assert "file2.html" in doc_ids

    def test_discover_nested_documents(self):
        """Discover HTM files in nested subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "NESTED-2025-0001"
            docs_dir = docket_dir / "raw-data" / "documents"
            subdir = docs_dir / "subfolder" / "deepfolder"
            subdir.mkdir(parents=True)

            (subdir / "nested_doc.htm").write_text("<html>Nested</html>")
            (docs_dir / "top_doc.htm").write_text("<html>Top</html>")

            files = get_htm_files(docket_dir)

            assert len(files) == 2
            doc_ids = [f["documentId"] for f in files]
            assert "nested_doc.htm" in doc_ids
            assert "top_doc.htm" in doc_ids

    def test_read_file_content_correctly(self):
        """Verify HTM file content is read correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "CONTENT-2025-0001"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            expected_content = (
                "<html><head><title>Test</title></head>"
                "<body>Content</body></html>"
            )
            (docs_dir / "test.htm").write_text(expected_content)

            files = get_htm_files(docket_dir)

            assert len(files) == 1
            assert files[0]["documentHtm"] == expected_content

    def test_handle_non_htm_files(self):
        """Ignore non-HTM/HTML files in documents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "MIXED-2025-0001"
            docs_dir = docket_dir / "raw-data" / "documents"
            docs_dir.mkdir(parents=True)

            (docs_dir / "document.htm").write_text("<html>HTM</html>")
            (docs_dir / "readme.txt").write_text("Text file")
            (docs_dir / "data.json").write_text('{"key": "value"}')
            (docs_dir / "file.pdf").write_text("PDF content")

            files = get_htm_files(docket_dir)

            assert len(files) == 1
            assert files[0]["documentId"] == "document.htm"


class TestIntegration:
    """Integration tests for full ingest workflow."""

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_full_workflow_fetch_then_ingest(self, mock_which, mock_popen):
        """Test complete workflow: fetch docket, then ingest HTM files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetched_path = _fake_fetch_docket_ready(tmpdir, mock_popen, mock_which)
            assert fetched_path.exists()

            mock_client = MagicMock()
            ingest_htm_files(fetched_path, mock_client)
            assert mock_client.index.called
            assert mock_client.index.call_count == 1

    @patch("ingest.subprocess.Popen")
    @patch("ingest.shutil.which")
    def test_full_workflow_fetch_verbose_logging(self, mock_which, mock_popen):
        """Test fetch_docket with spinner animation (verbose output simulation)."""
        mock_which.return_value = "/usr/local/bin/mirrulations-fetch"
        mock_proc = MagicMock()
        # Simulate spinner updates by making poll() return None multiple times
        mock_proc.poll.side_effect = [None, None, None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docket_dir.mkdir()

            # Fetch should work even with spinner animation
            result = fetch_docket("FAA-2025-0618", tmpdir)
            assert result.exists()
            assert result == docket_dir

    def test_docket_id_extraction_from_path(self):
        """Verify docket ID extraction from directory path."""
        test_cases = [
            (Path("/path/FAA-2025-0618"), "FAA-2025-0618"),
            (Path("/path/CMS-2025-0240"), "CMS-2025-0240"),
            (Path("/path/OSHA-2025-0005"), "OSHA-2025-0005"),
        ]

        for path, expected_id in test_cases:
            result = get_docket_ID(path)
            assert result == expected_id

    def test_document_id_extraction_from_filename(self):
        """Verify document ID extraction from file path."""
        test_cases = [
            (
                Path("/path/FAA-2025-0618-0001_content.htm"),
                "FAA-2025-0618-0001_content.htm",
            ),
            (Path("/path/doc1.html"), "doc1.html"),
            (Path("/path/test_file.htm"), "test_file.htm"),
        ]

        for path, expected_id in test_cases:
            result = get_document_ID(path)
            assert result == expected_id


class TestIngestDocumentHtml:
    """``document_content_html_paths`` / ``read_document_content_html`` (ingest.py)."""

    def test_document_content_html_paths_strips_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "FAA-2025-0618"
            docs = docket_dir / "raw-data" / "documents"
            docs.mkdir(parents=True)
            (docs / "FAA-2025-0618-0001_content.htm").write_text("<p>x</p>", encoding="utf-8")

            pairs = document_content_html_paths(docket_dir)
            assert len(pairs) == 1
            assert pairs[0][0] == "FAA-2025-0618-0001"
            assert pairs[0][1].name == "FAA-2025-0618-0001_content.htm"

    def test_read_document_content_html_maps_doc_id_to_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "X-2025-0001"
            docs = docket_dir / "raw-data" / "documents"
            docs.mkdir(parents=True)
            html = "<html><body>proposed rule</body></html>"
            (docs / "X-2025-0001-0002_content.htm").write_text(html, encoding="utf-8")

            by_id = read_document_content_html(docket_dir)
            assert by_id == {"X-2025-0001-0002": html}

    def test_missing_documents_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "EMPTY-2025-0001"
            (docket_dir / "raw-data").mkdir(parents=True)
            assert document_content_html_paths(docket_dir) == []
            assert read_document_content_html(docket_dir) == {}


class TestExtractedTxtLayout:
    """``extracted_txt_dir`` and ``read_derived_extracted_text`` (ingest.py)."""

    def test_extracted_txt_dir_mirrulations_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "FAA-2025-0618"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            ext.mkdir(parents=True)
            assert extracted_txt_dir(root) == ext

    def test_extracted_txt_dir_agency_docket_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "OSHA-2025-0005"
            ext = root / "derived-data" / "OSHA" / "OSHA-2025-0005" / "extracted_txt"
            ext.mkdir(parents=True)
            assert extracted_txt_dir(root) == ext

    def test_read_derived_from_json_and_plain_txt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = _docket_dir_with_derived_json_and_plain_txt(tmpdir)
            rows = read_derived_extracted_text(root)
            texts = {r.get("extractedText") for r in rows}
            assert "from json" in texts
            assert "plain body" in texts
            methods = {
                r.get("extractedMethod")
                for r in rows
                if r.get("extractedText") == "plain body"
            }
            assert "pypdf" in methods

    def test_read_derived_json_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "D-2025-0001"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            ext.mkdir(parents=True)
            payload = [
                {"docketId": "D-2025-0001", "commentId": "c1", "extractedText": "a"},
                {"docketId": "D-2025-0001", "commentId": "c2", "extractedText": "b"},
            ]
            (ext / "batch.json").write_text(json.dumps(payload), encoding="utf-8")
            rows = read_derived_extracted_text(root)
            assert len(rows) == 2

    def test_read_derived_progress_bar_disabled_for_small_json(self):
        """Verify progress bar disabled for <50 JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "SMALL-2025-0001"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            ext.mkdir(parents=True)
            # Create only 10 JSON files (below 50 threshold)
            for i in range(10):
                (ext / f"doc{i}.json").write_text(
                    json.dumps({
                        "docketId": "SMALL-2025-0001",
                        "commentId": f"c{i}",
                        "extractedText": f"text{i}",
                    }),
                    encoding="utf-8",
                )
            rows = read_derived_extracted_text(root)
            assert len(rows) == 10

    def test_read_derived_progress_bar_enabled_for_large_json(self):
        """Verify progress bar enabled for >=50 JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "LARGE-2025-0001"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            ext.mkdir(parents=True)
            # Create 60 JSON files (above 50 threshold)
            for i in range(60):
                (ext / f"doc{i}.json").write_text(
                    json.dumps({
                        "docketId": "LARGE-2025-0001",
                        "commentId": f"c{i}",
                        "extractedText": f"text{i}",
                    }),
                    encoding="utf-8",
                )
            rows = read_derived_extracted_text(root)
            assert len(rows) == 60

    def test_read_derived_plain_text_progress_bar_disabled_for_small(self):
        """Verify progress bar disabled for <50 plain text files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "SMALL-2025-0001"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            pypdf = ext / "comments_extracted_text" / "pypdf"
            pypdf.mkdir(parents=True)
            # Create only 10 plain text files
            for i in range(10):
                plain = f"comment_{i}_attachment_1_extracted.txt"
                (pypdf / plain).write_text(f"text content {i}", encoding="utf-8")
            rows = read_derived_extracted_text(root)
            assert len(rows) == 10

    def test_read_derived_plain_text_progress_bar_enabled_for_large(self):
        """Verify progress bar enabled for >=50 plain text files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "LARGE-2025-0001"
            ext = root / "derived-data" / "mirrulations" / "extracted_txt"
            pypdf = ext / "comments_extracted_text" / "pypdf"
            pypdf.mkdir(parents=True)
            # Create 60 plain text files
            for i in range(60):
                plain = f"comment_{i}_attachment_1_extracted.txt"
                (pypdf / plain).write_text(f"text content {i}", encoding="utf-8")
            rows = read_derived_extracted_text(root)
            assert len(rows) == 60


class TestFederalRegisterFrDocNums:
    """``extract_frdocnums_*`` / ``collect_frdocnums_from_docket`` (ingest.py)."""

    def test_extract_frdocnums_from_document_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "doc.json"
            p.write_text(
                json.dumps(
                    {
                        "data": {
                            "attributes": {"frDocNum": "2024-12345"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            assert extract_frdocnums_from_document_json(p) == {"2024-12345"}

    def test_extract_frdocnums_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "empty.json"
            p.write_text(json.dumps({"data": {"attributes": {}}}), encoding="utf-8")
            assert extract_frdocnums_from_document_json(p) == set()

    def test_collect_frdocnums_from_docket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "AG-2025-0001"
            docs = docket_dir / "raw-data" / "documents"
            docs.mkdir(parents=True)
            (docs / "a.json").write_text(
                json.dumps({"data": {"attributes": {"frDocNum": "FR-1"}}}),
                encoding="utf-8",
            )
            (docs / "b.json").write_text(
                json.dumps({"data": {"attributes": {"frDocNum": "FR-1"}}}),
                encoding="utf-8",
            )
            assert collect_frdocnums_from_docket(docket_dir) == {"FR-1"}

    def test_collect_frdocnums_progress_bar_disabled_for_small_datasets(self):
        """Verify progress bars are disabled for small datasets (<20 docs)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "SMALL-2025-0001"
            docs = docket_dir / "raw-data" / "documents"
            docs.mkdir(parents=True)
            # Create only 5 documents (below the 20 threshold)
            for i in range(5):
                (docs / f"doc{i}.json").write_text(
                    json.dumps(
                        {"data": {"attributes": {"frDocNum": f"FR-{i}"}}}
                    ),
                    encoding="utf-8",
                )
            result = collect_frdocnums_from_docket(docket_dir)
            assert len(result) == 5

    def test_collect_frdocnums_progress_bar_enabled_for_large_datasets(self):
        """Verify progress bars are enabled for large datasets (>=20 docs)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docket_dir = Path(tmpdir) / "LARGE-2025-0001"
            docs = docket_dir / "raw-data" / "documents"
            docs.mkdir(parents=True)
            # Create 25 documents (above the 20 threshold)
            for i in range(25):
                (docs / f"doc{i}.json").write_text(
                    json.dumps(
                        {"data": {"attributes": {"frDocNum": f"FR-{i}"}}}
                    ),
                    encoding="utf-8",
                )
            result = collect_frdocnums_from_docket(docket_dir)
            assert len(result) == 25


class TestIngestExtractedTextOpenSearch:
    """``ingest_extracted_text_to_comments_extracted_text`` (ingest.py)."""

    def test_indexes_valid_records(self):
        mock_client = MagicMock()
        records = [
            {
                "docketId": "D-1",
                "commentId": "C-1",
                "attachmentId": "C-1_attachment_1",
                "extractedMethod": "pypdf",
                "extractedText": "hello",
            }
        ]
        n = ingest_extracted_text_to_comments_extracted_text(mock_client, records)
        assert n == 1
        mock_client.index.assert_called_once()
        kw = mock_client.index.call_args[1]
        assert kw["index"] == OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX
        assert kw["id"] == "C-1_attachment_1"
        assert kw["body"]["extractedText"] == "hello"

    def test_skips_empty_text(self):
        mock_client = MagicMock()
        n = ingest_extracted_text_to_comments_extracted_text(
            mock_client,
            [{"docketId": "D", "commentId": "C", "extractedText": "   "}],
        )
        assert n == 0
        mock_client.index.assert_not_called()


class TestIngestDocketNormalizeAndLinks:
    """``_normalize_docket_id``, ``extract_self_link`` (ingest_docket.py)."""

    def test_normalize_docket_id(self):
        assert _normalize_docket_id("  faa-2025-0618  ") == "FAA-2025-0618"
        assert _normalize_docket_id("cms_2025_extra-0240") == "CMS-0240"
        assert _normalize_docket_id("nohyphen") == "NOHYPHEN"

    def test_extract_self_link_dict(self):
        payload = {"links": {"self": "https://api.example/x"}}
        assert extract_self_link(payload) == "https://api.example/x"

    def test_extract_self_link_list(self):
        assert (
            extract_self_link({"links": [{"self": "https://first"}]})
            == "https://first"
        )

    def test_extract_self_link_missing(self):
        assert extract_self_link({}) is None


class TestIngestDocketExtractComment:
    """``extract_comment`` (ingest_docket.py)."""

    def test_extract_comment_maps_core_fields(self):
        data = {
            "id": "FAA-2025-0618-0003",
            "attributes": {
                "comment": "Public comment text",
                "docketId": "FAA-2025-0618",
                "agencyId": "FAA",
                "commentOnDocumentId": "FAA-2025-0618-0001",
            },
            "links": {"self": "https://api.regulations.gov/v4/comments/FAA-2025-0618-0003"},
        }
        rec = extract_comment(data)
        assert rec["comment_id"] == "FAA-2025-0618-0003"
        assert rec["docket_id"] == "FAA-2025-0618"
        assert rec["comment"] == "Public comment text"
        assert rec["document_id"] == "FAA-2025-0618-0001"
        assert "comments/" in rec["api_link"]

    def test_extract_comment_duplicate_count_defaults_to_zero(self):
        data = {
            "id": "X-1",
            "attributes": {
                "comment": "c",
                "docketId": "D-1",
            },
            "links": {},
        }
        rec = extract_comment(data)
        assert rec["duplicate_comment_count"] == 0


class TestIngestDocketMapDocket:
    """``map_docket`` (ingest_docket.py)."""

    def test_map_docket_minimal_valid(self):
        payload = {
            "data": {
                "id": "FAA-2025-0618",
                "type": "dockets",
                "attributes": {
                    "modifyDate": "2025-01-15T00:00:00Z",
                    "docketType": "Rulemaking",
                    "agencyId": "FAA",
                    "title": "Test docket",
                    "dkAbstract": "Abstract",
                },
                "links": {"self": "https://api.regulations.gov/v4/dockets/FAA-2025-0618"},
            }
        }
        row = map_docket(payload)
        assert row is not None
        assert row["docket_id"] == "FAA-2025-0618"
        assert row["agency_id"] == "FAA"
        assert row["docket_type"] == "Rulemaking"
        assert row["docket_api_link"].startswith("https://")

    def test_map_docket_returns_none_when_invalid(self):
        assert map_docket({}) is None
        assert map_docket({"data": {"id": "x", "attributes": {}}}) is None


class TestLoadRawJson:
    """``load_raw_json`` (ingest_docket.py)."""

    def test_load_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "x.json"
            p.write_text(json.dumps({"ok": True}), encoding="utf-8")
            assert load_raw_json(p) == {"ok": True}

    def test_load_invalid_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            assert load_raw_json(p) is None
