"""Regression contracts for the English/Korean browser-side language selector."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_language_selector_and_script_order():
    page = TestClient(app).get("/")
    assert page.status_code == 200
    markup = page.text
    assert '<html lang="en">' in markup
    assert 'id="uiLanguage"' in markup
    assert '<option value="en">English</option>' in markup
    assert '<option value="ko">한국어</option>' in markup
    assert markup.index('<script src="/i18n.js">') < markup.index('<script src="/app.js">')

    asset = TestClient(app).get("/i18n.js")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]
    assert "stellarDataExporter.uiLanguage.v1" in asset.text
    assert "MutationObserver" in asset.text
    assert "sessionStorage.setItem" not in asset.text


def test_language_selector_preserves_query_and_connection_inputs():
    script = (STATIC / "i18n.js").read_text()
    app_js = (STATIC / "app.js").read_text()
    assert '"script,style,textarea,pre,code,#previewTable td,#previewTable th,[contenteditable],[data-no-translate]"' in script
    assert 'element.setAttribute(attribute, rendered)' in script
    assert 'document.documentElement.lang = language' in script
    assert 'localStorage.setItem(STORAGE_KEY, language)' in script
    assert 'window.ExporterI18n?.sourceText(button)' in app_js
    assert 'sessionStorage.setItem(CONNECTION_SESSION_STORAGE_KEY' in app_js
    assert 'sessionStorage.setItem(ACTIVE_EXPORT_SESSION_STORAGE_KEY' in app_js


def test_korean_covers_main_workflows_and_messages():
    dictionary = (STATIC / "i18n.js").read_text()
    for english, korean in (
        ("Run export", "내보내기 실행"),
        ("Test connection", "연결 테스트"),
        ("Data sources", "데이터 소스"),
        ("Export History", "내보내기 기록"),
        ("SFTP host is required.", "SFTP 호스트를 입력하세요."),
        ("Query must be a JSON object.", "쿼리는 JSON 객체여야 합니다."),
        ("The exporter service could not be reached after automatic retries.", "자동 재시도"),
    ):
        assert english in dictionary
        assert korean in dictionary
