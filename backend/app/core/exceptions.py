from fastapi import HTTPException, status

class NotFoundException(HTTPException):
    def __init__(self, detail: str = "Not Found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class UnauthorizedException(HTTPException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

class ForbiddenException(HTTPException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class ValidationException(HTTPException):
    def __init__(self, detail: str = "Validation Error"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

class IngestException(HTTPException):
    def __init__(self, detail: str = "Ingestion Error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
