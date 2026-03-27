import pytest
from pe_common.schemas import success_response, paginated_response, ApiResponse
from pe_common.exceptions import AppException, NotFoundError


def test_success_response_shape():
    result = success_response({"key": "value"})
    assert result["success"] is True
    assert result["data"] == {"key": "value"}
    assert "request_id" in result["meta"]
    assert "timestamp" in result["meta"]


def test_success_response_custom_meta():
    custom_meta = {"request_id": "test-id", "timestamp": "2024-01-01T00:00:00"}
    result = success_response({"key": "value"}, meta=custom_meta)
    assert result["meta"]["request_id"] == "test-id"


def test_success_response_none_data():
    result = success_response(None)
    assert result["success"] is True
    assert result["data"] is None


def test_paginated_response_shape():
    data = [{"id": 1}, {"id": 2}]
    result = paginated_response(data=data, page=1, page_size=10, total=25)
    assert result["success"] is True
    assert result["data"] == data
    assert result["meta"]["pagination"]["page"] == 1
    assert result["meta"]["pagination"]["page_size"] == 10
    assert result["meta"]["pagination"]["total"] == 25
    assert result["meta"]["pagination"]["total_pages"] == 3


def test_paginated_response_total_pages_exact():
    result = paginated_response(data=[], page=1, page_size=10, total=20)
    assert result["meta"]["pagination"]["total_pages"] == 2


def test_paginated_response_total_pages_single():
    result = paginated_response(data=[], page=1, page_size=10, total=5)
    assert result["meta"]["pagination"]["total_pages"] == 1


def test_paginated_response_total_pages_zero():
    result = paginated_response(data=[], page=1, page_size=10, total=0)
    assert result["meta"]["pagination"]["total_pages"] == 0


def test_app_exception_attributes():
    exc = AppException(code="TEST_ERROR", message="Test message", status_code=400, details={"field": "value"})
    assert exc.code == "TEST_ERROR"
    assert exc.message == "Test message"
    assert exc.status_code == 400
    assert exc.details == {"field": "value"}


def test_app_exception_default_details():
    exc = AppException(code="TEST_ERROR", message="Test message")
    assert exc.details == {}
    assert exc.status_code == 400


def test_not_found_error_status_code():
    exc = NotFoundError(resource="User")
    assert exc.status_code == 404
    assert exc.code == "NOT_FOUND"
    assert "User" in exc.message


def test_not_found_error_with_resource_id():
    exc = NotFoundError(resource="Product", resource_id="abc-123")
    assert exc.status_code == 404
    assert "abc-123" in exc.message


def test_not_found_error_without_resource_id():
    exc = NotFoundError(resource="Order")
    assert "not found" in exc.message
    assert "None" not in exc.message