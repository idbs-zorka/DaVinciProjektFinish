class APIError(IOError):
    """
    Wyjątek reprezentujący błąd specyficzny dla API GIOŚ.

    Zawiera szczegółowe informacje o błędzie zwróconym przez API:
    - kod błędu (`code`),
    - przyczyna (`reason`),
    - wynik (`result`),
    - możliwe rozwiązanie (`solution`).
    """

    def __init__(self, code,reason,result,solution):
        self.code = code
        self.reason = reason
        self.result = result
        self.solution = solution

    def __str__(self):
        return f"API Error [{self.code}]: {self.reason} {self.result} {self.solution}"

class TooManyRequests(IOError):
    """
    Wyjątek reprezentujący błąd API GIOŚ zbyt wielu żadań
    """
    pass