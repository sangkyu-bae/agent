"""Tests for DBQueryListener."""

import pytest
from unittest.mock import MagicMock, patch, call


from src.infrastructure.logging.db_query_listener import (
    DBQueryListener,
    _mask_sensitive_params,
)


class TestMaskSensitiveParams:
    """_mask_sensitive_params() 함수 단위 테스트."""

    def test_masks_password(self):
        """password 키 값이 마스킹된다."""
        result = _mask_sensitive_params({"password": "secret123"})
        assert result["password"] == "***MASKED***"

    def test_masks_token(self):
        """token 키 값이 마스킹된다."""
        result = _mask_sensitive_params({"token": "bearer_xyz"})
        assert result["token"] == "***MASKED***"

    def test_masks_secret(self):
        """secret 키 값이 마스킹된다."""
        result = _mask_sensitive_params({"secret": "my_secret"})
        assert result["secret"] == "***MASKED***"

    def test_masks_api_key(self):
        """api_key 키 값이 마스킹된다."""
        result = _mask_sensitive_params({"api_key": "sk-1234"})
        assert result["api_key"] == "***MASKED***"

    def test_masks_refresh_token(self):
        """refresh_token 키 값이 마스킹된다."""
        result = _mask_sensitive_params({"refresh_token": "rt-abc"})
        assert result["refresh_token"] == "***MASKED***"

    def test_non_sensitive_not_masked(self):
        """일반 키는 마스킹되지 않는다."""
        result = _mask_sensitive_params({"user_id": "user_123", "email": "a@b.com"})
        assert result["user_id"] == "user_123"
        assert result["email"] == "a@b.com"

    def test_mixed_params(self):
        """민감 키와 일반 키가 혼합된 경우 민감 키만 마스킹된다."""
        params = {"email_1": "user@example.com", "password": "secret"}
        result = _mask_sensitive_params(params)
        assert result["email_1"] == "user@example.com"
        assert result["password"] == "***MASKED***"

    def test_list_of_dicts(self):
        """executemany 형태(list of dict)도 처리한다."""
        params = [
            {"password": "pw1", "name": "Alice"},
            {"password": "pw2", "name": "Bob"},
        ]
        result = _mask_sensitive_params(params)
        assert result[0]["password"] == "***MASKED***"
        assert result[0]["name"] == "Alice"
        assert result[1]["password"] == "***MASKED***"
        assert result[1]["name"] == "Bob"

    def test_none_params(self):
        """None 파라미터는 None을 반환한다."""
        result = _mask_sensitive_params(None)
        assert result is None

    def test_empty_dict(self):
        """빈 dict는 빈 dict를 반환한다."""
        result = _mask_sensitive_params({})
        assert result == {}

    def test_case_insensitive_key(self):
        """키는 소문자 비교로 마스킹된다 (PASSWORD → 마스킹)."""
        result = _mask_sensitive_params({"PASSWORD": "secret"})
        assert result["PASSWORD"] == "***MASKED***"


class TestDBQueryListenerBeforeAfter:
    """DBQueryListener before/after execute 이벤트 테스트."""

    def _make_conn(self):
        """conn.info dict를 가진 Mock 연결 객체 생성."""
        conn = MagicMock()
        conn.info = {}
        return conn

    def test_before_execute_records_start_time(self):
        """before_cursor_execute 호출 시 conn.info에 시작 시간이 기록된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        listener._before_execute(conn, None, "SELECT 1", {}, None, False)
        assert "query_start_time" in conn.info
        assert isinstance(conn.info["query_start_time"], float)

    def test_after_execute_logs_sql(self):
        """after_cursor_execute 호출 시 SQL 문이 로그에 포함된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT users.id FROM users WHERE users.id = :id_1"

        listener._before_execute(conn, None, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, {"id_1": 1}, None, False)
            mock_logger.debug.assert_called_once()
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["sql"] == sql.strip()

    def test_after_execute_logs_duration_ms(self):
        """after_cursor_execute 호출 시 duration_ms가 양수로 로깅된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1"

        listener._before_execute(conn, None, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["duration_ms"] is not None
            assert call_kwargs["duration_ms"] >= 0

    def test_after_execute_masks_sensitive_params(self):
        """after_cursor_execute 호출 시 민감 파라미터가 마스킹된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1 WHERE password = :password"
        params = {"password": "secret"}

        listener._before_execute(conn, None, sql, params, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, params, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["params"]["password"] == "***MASKED***"

    def test_after_execute_non_sensitive_params_not_masked(self):
        """민감하지 않은 파라미터는 마스킹되지 않는다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1 WHERE email = :email_1"
        params = {"email_1": "user@example.com"}

        listener._before_execute(conn, None, sql, params, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, params, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["params"]["email_1"] == "user@example.com"

    def test_after_execute_strips_whitespace_from_sql(self):
        """SQL 문의 앞뒤 공백이 제거된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "  \n  SELECT 1  \n  "

        listener._before_execute(conn, None, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["sql"] == "SELECT 1"

    def test_after_execute_debug_level_message(self):
        """로그 메시지는 'DB Query'이다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1"

        listener._before_execute(conn, None, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, None, sql, {}, None, False)
            call_args = mock_logger.debug.call_args[0]
            assert call_args[0] == "DB Query"

    def _make_cursor(self, rowcount=1, description=None):
        """rowcount와 description을 가진 Mock cursor 생성."""
        cursor = MagicMock()
        cursor.rowcount = rowcount
        cursor.description = description
        return cursor

    def test_after_execute_logs_row_count_for_dml(self):
        """DML(INSERT/UPDATE/DELETE) 실행 후 영향받은 행 수가 로깅된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "INSERT INTO users (email) VALUES (:email_1)"
        cursor = self._make_cursor(rowcount=1, description=None)

        listener._before_execute(conn, cursor, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, cursor, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["row_count"] == 1

    def test_after_execute_logs_columns_for_select(self):
        """SELECT 실행 후 반환된 컬럼명 목록이 로깅된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT id, email FROM users"
        # cursor.description: tuple of (name, ...) per column
        description = [("id", None, None, None, None, None, None),
                       ("email", None, None, None, None, None, None)]
        cursor = self._make_cursor(rowcount=2, description=description)

        listener._before_execute(conn, cursor, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, cursor, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["columns"] == ["id", "email"]

    def test_after_execute_columns_none_for_dml(self):
        """DML 실행 후 columns는 None이다 (description이 없으므로)."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "UPDATE users SET email = :email WHERE id = :id"
        cursor = self._make_cursor(rowcount=1, description=None)

        listener._before_execute(conn, cursor, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, cursor, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["columns"] is None

    def test_after_execute_row_count_minus_one_still_logged(self):
        """rowcount가 -1 (드라이버 미지원)인 경우에도 그대로 로깅된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1"
        cursor = self._make_cursor(rowcount=-1, description=[("1", None, None, None, None, None, None)])

        listener._before_execute(conn, cursor, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, cursor, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["row_count"] == -1

    def test_after_execute_cursor_without_rowcount_attr(self):
        """cursor에 rowcount 속성이 없어도 오류 없이 None으로 처리된다."""
        listener = DBQueryListener()
        conn = self._make_conn()
        sql = "SELECT 1"

        # rowcount 속성이 없는 cursor
        cursor = MagicMock(spec=[])  # 아무 속성도 없는 Mock

        listener._before_execute(conn, cursor, sql, {}, None, False)

        with patch("src.infrastructure.logging.db_query_listener.logger") as mock_logger:
            listener._after_execute(conn, cursor, sql, {}, None, False)
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["row_count"] is None


class TestDBQueryListenerRegister:
    """DBQueryListener.register() 이벤트 등록 테스트."""

    def test_register_attaches_listeners(self):
        """register() 호출 시 SQLAlchemy 이벤트가 등록된다."""
        from unittest.mock import patch, MagicMock

        listener = DBQueryListener()
        mock_engine = MagicMock()
        mock_sync_engine = MagicMock()
        mock_engine.sync_engine = mock_sync_engine

        with patch("src.infrastructure.logging.db_query_listener.event") as mock_event:
            listener.register(mock_engine)
            assert mock_event.listen.call_count == 2

            # before_cursor_execute와 after_cursor_execute 모두 등록 확인
            listen_calls = mock_event.listen.call_args_list
            event_names = [c[0][1] for c in listen_calls]
            assert "before_cursor_execute" in event_names
            assert "after_cursor_execute" in event_names
