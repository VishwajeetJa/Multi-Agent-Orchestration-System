"""
Integration tests for the Flask API endpoints.
Run with: pytest tests/test_api.py -v
Requires Redis to be running for full integration tests.
"""
import pytest
from unittest.mock import MagicMock, patch
from core.schemas import SessionState, TaskStatus


@pytest.fixture
def client():
    """Create a Flask test client."""
    with patch('api.routes._memory') as mock_mem:
        from app_new import create_app
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c, mock_mem


class TestHealthEndpoint:
    def test_health_check_returns_200(self, client):
        c, mock_mem = client
        mock_mem.ping.return_value = True
        resp = c.get('/api/v1/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'healthy'

    def test_health_check_degraded_when_redis_down(self, client):
        c, mock_mem = client
        mock_mem.ping.return_value = False
        resp = c.get('/api/v1/health')
        assert resp.status_code == 503


class TestInfoEndpoint:
    def test_info_returns_agent_list(self, client):
        c, _ = client
        resp = c.get('/api/v1/info')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'agents' in data
        assert 'planner' in data['agents']


class TestWorkflowEndpoints:
    def test_start_workflow_requires_auth(self, client):
        c, _ = client
        resp = c.post('/api/v1/workflow', json={'query': 'test'})
        assert resp.status_code == 401

    def test_start_workflow_with_valid_api_key(self, client):
        c, mock_mem = client
        mock_mem.check_rate_limit.return_value = True
        mock_mem.save_session = MagicMock()

        with patch('api.routes.run_workflow_task') as mock_task:
            mock_task.apply_async.return_value = MagicMock(id='celery-task-123')
            resp = c.post(
                '/api/v1/workflow',
                json={'query': 'Tell me about quantum computing'},
                headers={'X-API-Key': 'dev-key-12345'},
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert 'session_id' in data
        assert data['status'] == 'accepted'

    def test_start_workflow_rate_limited(self, client):
        c, mock_mem = client
        mock_mem.check_rate_limit.return_value = False
        resp = c.post(
            '/api/v1/workflow',
            json={'query': 'test'},
            headers={'X-API-Key': 'dev-key-12345'},
        )
        assert resp.status_code == 429

    def test_get_status_not_found(self, client):
        c, mock_mem = client
        mock_mem.get_session.return_value = None
        resp = c.get(
            '/api/v1/workflow/nonexistent-id/status',
            headers={'X-API-Key': 'dev-key-12345'},
        )
        assert resp.status_code == 404

    def test_get_status_completed(self, client):
        c, mock_mem = client
        session = SessionState(
            user_query="Test",
            status=TaskStatus.COMPLETED,
            final_result="The final report",
        )
        mock_mem.get_session.return_value = session
        resp = c.get(
            f'/api/v1/workflow/{session.session_id}/status',
            headers={'X-API-Key': 'dev-key-12345'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'completed'
        assert data['result'] == "The final report"
