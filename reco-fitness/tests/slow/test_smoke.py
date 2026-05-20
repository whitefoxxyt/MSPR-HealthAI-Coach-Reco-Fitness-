"""
Smoke test slow -- tests reseau reels ou a execution longue.
Ces tests sont exclus de la CI standard.
Lancer avec : pytest -m slow
"""
import pytest


@pytest.mark.slow
def test_slow_marker_is_registered(request):
    """
    Verifie que le marker slow est bien configure et applique a ce test.
    Sert de placeholder -- ajouter ici les vrais tests reseau.
    """
    assert request.node.get_closest_marker("slow") is not None


@pytest.mark.slow
async def test_slow_async_placeholder(request):
    """Placeholder async pour les futurs tests d'appels externes reels."""
    import asyncio
    await asyncio.sleep(0)
    assert request.node.get_closest_marker("slow") is not None
