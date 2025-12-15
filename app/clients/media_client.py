import requests
import os
from typing import List, Optional, Dict


class MediaServiceClient:
    """Client to communicate with Media Storage Microservice"""

    def __init__(self):
        self.base_url = os.environ.get('MEDIA_SERVICE_URL', 'http://localhost:8001')
        self.timeout = 300  # 5 minutes for large files

    def _make_request(self, method: str, endpoint: str, **kwargs):
        """Make HTTP request with error handling"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling media service: {e}")
            raise Exception(f"Media service error: {str(e)}")

    def upload_thumbnail(self, file, user_id: str) -> Optional[str]:
        """Upload thumbnail image"""
        try:
            if hasattr(file, 'seek'):
                file.seek(0)

            file_content = file.read() if hasattr(file, 'read') else file
            filename = getattr(file, 'filename', 'thumbnail.jpg')
            content_type = getattr(file, 'content_type', None) or getattr(file, 'mimetype', 'image/jpeg')

            files = {'file': (filename, file_content, content_type)}
            data = {'user_id': user_id}

            result = self._make_request(
                'POST',
                '/api/upload/thumbnail',
                files=files,
                data=data,
                timeout=60
            )

            return result.get('url')
        except Exception as e:
            print(f"Error uploading thumbnail: {e}")
            return None

    def upload_video(
        self,
        file,
        user_id: str,
        lesson_id: Optional[str] = None,
        series_id: Optional[str] = None,
        create_transcript: bool = True
    ) -> Optional[Dict[str, str]]:
        """
        Upload video file với option tạo transcript

        Returns:
            Dict với url, key, transcript_status
        """
        try:
            if hasattr(file, 'seek'):
                file.seek(0)

            file_content = file.read() if hasattr(file, 'read') else file
            filename = getattr(file, 'filename', 'video.mp4')
            content_type = getattr(file, 'content_type', None) or getattr(file, 'mimetype', 'video/mp4')

            files = {'file': (filename, file_content, content_type)}
            data = {
                'user_id': user_id,
                'create_transcript': 'true' if create_transcript else 'false',
                'lesson_id': lesson_id or '',
                'series_id': series_id or ''
            }

            result = self._make_request(
                'POST',
                '/api/upload/video',
                files=files,
                data=data,
                timeout=self.timeout
            )

            # Return full result dict thay vì chỉ url
            return {
                "url": result.get('url'),
                "key": result.get('key'),
                "transcript_status": result.get('transcript_status', 'disabled')
            }
        except Exception as e:
            print(f"Error uploading video: {e}")
            return None

    def upload_document(self, file, user_id: str) -> Optional[str]:
        """Upload document file"""
        try:
            if hasattr(file, 'seek'):
                file.seek(0)

            file_content = file.read() if hasattr(file, 'read') else file
            filename = getattr(file, 'filename', 'document.pdf')
            content_type = getattr(file, 'content_type', None) or getattr(file, 'mimetype', 'application/pdf')

            files = {'file': (filename, file_content, content_type)}
            data = {'user_id': user_id}

            result = self._make_request(
                'POST',
                '/api/upload/document',
                files=files,
                data=data,
                timeout=120
            )

            return result.get('url')
        except Exception as e:
            print(f"Error uploading document: {e}")
            return None

    def upload_documents_batch(self, files: List, user_id: str) -> List[str]:
        """Upload multiple documents"""
        try:
            file_tuples = []
            for f in files:
                if hasattr(f, 'seek'):
                    f.seek(0)

                file_content = f.read() if hasattr(f, 'read') else f
                filename = getattr(f, 'filename', 'document.pdf')
                content_type = getattr(f, 'content_type', None) or getattr(f, 'mimetype', 'application/pdf')

                file_tuples.append(('files', (filename, file_content, content_type)))

            data = {'user_id': user_id}

            result = self._make_request(
                'POST',
                '/api/upload/documents/batch',
                files=file_tuples,
                data=data,
                timeout=self.timeout
            )

            return result.get('urls', [])
        except Exception as e:
            print(f"Error uploading documents: {e}")
            return []

    def delete_file(self, url_or_key: str) -> bool:
        """Delete a file"""
        try:
            result = self._make_request(
                'DELETE',
                '/api/delete',
                json={'url_or_key': url_or_key},
                timeout=30
            )

            return result.get('success', False)
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def delete_files_batch(self, urls: List[str]) -> Dict:
        """Delete multiple files"""
        try:
            result = self._make_request(
                'DELETE',
                '/api/delete/batch',
                json={'urls': urls},
                timeout=60
            )

            return {
                "deleted": result.get('deleted', []),
                "failed": result.get('failed', [])
            }
        except Exception as e:
            print(f"Error deleting files: {e}")
            return {"deleted": [], "failed": urls}

    def health_check(self) -> bool:
        """Check if media service is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
