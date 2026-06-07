# -*- coding: utf-8 -*-

class ApiException(Exception):
    status = 400
    error = "unknown_error"
    description = "Unknown error."

    def __init__(
            self,
            description=None,
            status=None,
            error=None,
    ):
        if description:
            self.description = description

        if status:
            self.status = status

        if error:
            self.error = error

        super().__init__(self.description)

    def to_dict(self):
        return {
            "success": False,
            "error": self.error,
            "error_description": self.description,
        }



class ValidationException(ApiException):
    status = 400
    error = "invalid_data"



class UnauthorizedException(ApiException):
    status = 401
    error = "unauthorized"
    description = "Authentication required."


class ForbiddenException(ApiException):
    status = 403
    error = "forbidden"
    description = "Access denied."


class InvalidScopeException(ApiException):
    status = 403
    error = "forbidden"
    description = "Invalid Scope"

