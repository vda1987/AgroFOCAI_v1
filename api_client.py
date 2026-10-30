from __future__ import annotations
import requests


def interpret(api_url: str, api_token: str, text: str, previous_graph: dict | None, timeout: int = 240) -> dict:
    url = api_url.rstrip('/') + '/interpret'
    r = requests.post(
        url,
        json={'text': text, 'previous_graph': previous_graph},
        headers={'Authorization': f'Bearer {api_token}'},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def health(api_url: str, timeout: int = 10) -> dict:
    r = requests.get(api_url.rstrip('/') + '/health', timeout=timeout)
    r.raise_for_status()
    return r.json()
