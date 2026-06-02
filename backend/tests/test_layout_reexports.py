"""backend/app/* re-export integrity.

Контракт: импорты из template-layout эквивалентны прямым импортам
из `lot_orchestrator{,_web}`. Никакой логики не должно появляться в
`backend/app/*` — только re-export.
"""
from __future__ import annotations


def test_main_app_is_lot_orchestrator_web_app():
    from backend.app.main import app, create_app
    from lot_orchestrator_web.main import app as direct_app, create_app as direct_create
    assert app is direct_app
    assert create_app is direct_create


def test_main_app_has_expected_routes():
    from backend.app.main import app
    paths = sorted({route.path for route in app.routes})
    expected = {
        "/",
        "/lots/{lot_id}/run",
        "/lots/{lot_id}/status/{run_id}",
        "/lots/{lot_id}/needs-input",
        "/lots/{lot_id}/provide-input",
        "/lots/{lot_id}/artifacts",
    }
    assert expected.issubset(set(paths))


def test_api_deps_reexport():
    from backend.app.api.deps import get_store, reset_store_for_tests
    from lot_orchestrator_web.store import get_store as direct_get
    from lot_orchestrator_web.store import reset_store_for_tests as direct_reset
    assert get_store is direct_get
    assert reset_store_for_tests is direct_reset


def test_core_settings_reexport():
    from backend.app.core.config import Settings
    from lot_orchestrator.config import Settings as DirectSettings
    assert Settings is DirectSettings


def test_core_security_install_basic_auth_exists():
    from backend.app.core.security import install_basic_auth
    # Сама функция доступна; на main без PR #93 вернёт False (lazy ImportError swallow).
    assert callable(install_basic_auth)


def test_core_persistence_proxy_class_exists():
    from backend.app.core.persistence import SQLitePersistence
    assert SQLitePersistence is not None


def test_crud_runs_reexport():
    from backend.app.crud.runs import Run, RunStore, get_store, reset_store_for_tests
    from lot_orchestrator_web.store import (
        Run as DRun,
        RunStore as DStore,
        get_store as dget,
        reset_store_for_tests as dreset,
    )
    assert Run is DRun
    assert RunStore is DStore
    assert get_store is dget
    assert reset_store_for_tests is dreset


def test_models_schemas_reexport():
    from backend.app.models.schemas import (
        AssetData, Conflict, DocumentDate, EgrnLayer, Entity, EtpProfile,
        Fact, Provenance, TargetScenario,
    )
    from lot_orchestrator.schemas import AssetData as DAssetData
    assert AssetData is DAssetData
    # Ensure все имена импортируются без ошибок.
    for cls in (Conflict, DocumentDate, EgrnLayer, Entity, EtpProfile,
                Fact, Provenance, TargetScenario):
        assert cls is not None


def test_services_orchestrator_reexport():
    from backend.app.services.orchestrator import (
        OrchestrationResult, Phase, run_pipeline,
    )
    from lot_orchestrator.state_machine import (
        OrchestrationResult as DRes,
        Phase as DPhase,
        run_pipeline as drun,
    )
    assert OrchestrationResult is DRes
    assert Phase is DPhase
    assert run_pipeline is drun


def test_services_llm_reexport():
    from backend.app.services.llm import (
        AnthropicClient, LLMClient, LLMResponse, MockClient,
    )
    from lot_orchestrator.llm_client import (
        AnthropicClient as DAnthropic,
        MockClient as DMock,
    )
    assert AnthropicClient is DAnthropic
    assert MockClient is DMock


def test_package_init_no_logic():
    """Sanity: backend.app не имеет state / экспортируемых функций кроме `app`/`create_app`."""
    import backend.app as pkg
    # Только docstring + ничего другого на уровне пакета.
    assert hasattr(pkg, "__doc__")
    # Никаких dunders с runtime-логикой.
    for forbidden in ("init_db", "create_engine", "Settings", "RunStore"):
        assert not hasattr(pkg, forbidden), \
            f"backend.app.__init__ не должен экспортировать {forbidden} напрямую"


def test_install_basic_auth_with_dummy_app():
    """install_basic_auth работает без ошибки даже если PR #93 ещё не merged."""
    from backend.app.core.security import install_basic_auth
    from fastapi import FastAPI
    app = FastAPI()
    result = install_basic_auth(app)
    # На main (без PR #93) функция не падает; возвращает True или False
    # в зависимости от того, доступен ли модуль auth (после merge — True
    # при наличии env, иначе False).
    assert isinstance(result, bool)
