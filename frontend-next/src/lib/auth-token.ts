let _authToken: string | null = null;

export function setAuthToken(token: string | null | undefined): void {
  _authToken = token ?? null;
}

export function getAuthToken(): string | null {
  return _authToken;
}
