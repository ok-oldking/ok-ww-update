"""Translations for the update window, in the PyAppify launcher's languages.

The language list and the way an OS locale picks one of them match the
launcher (``get_default_lang_from_locale`` in its ``config_manager.rs``), so an
app shows the same language in the launcher and in this window. The launcher
passes its choice to the app as ``PYAPPIFY_LOCALE``.
"""
import os
import subprocess
import sys

EN = "en"
ZH_CN = "zh-CN"
ZH_TW = "zh-TW"
ES = "es"
JA = "ja"
KO = "ko"
LANGUAGES = (EN, ZH_CN, ZH_TW, ES, JA, KO)
LANGUAGE_NAMES = {
    EN: "English",
    ZH_CN: "简体中文",
    ZH_TW: "繁體中文",
    ES: "Español",
    JA: "日本語",
    KO: "한국어",
}


def normalize_locale(locale):
    """``zh_CN.UTF-8`` -> ``zh-CN``: no encoding or modifier, dashes, region upper case."""
    if not locale:
        return ""
    locale = str(locale).split(".", 1)[0].split("@", 1)[0].replace("_", "-").strip()
    parts = [part for part in locale.split("-") if part]
    if not parts:
        return ""
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        normalized.append(part.upper() if len(part) == 2 else part.title())
    return "-".join(normalized)


def language_from_locale(locale):
    """The launcher language for an OS locale such as ``zh-CN`` or ``ja_JP``.

    As the launcher: ``zh-CN`` is Simplified Chinese, ``zh-TW`` and ``zh-HK``
    Traditional Chinese, ``es*``, ``ja*`` and ``ko*`` their languages and
    everything else English. Script subtags (``zh-Hans``, ``zh-Hant``, as
    macOS reports them) are also understood.
    """
    locale = normalize_locale(locale)
    if locale in (ZH_CN, "zh-SG") or locale.startswith("zh-Hans"):
        return ZH_CN
    if locale in (ZH_TW, "zh-HK", "zh-MO") or locale.startswith("zh-Hant"):
        return ZH_TW
    for language in (ES, JA, KO):
        if locale == language or locale.startswith(language + "-"):
            return language
    return EN


def match_language(value):
    """``value`` as one of ``LANGUAGES`` if it names one exactly, else None."""
    normalized = normalize_locale(value)
    return normalized if normalized in LANGUAGES else None


def system_locale():
    """The user's OS locale, such as ``zh-CN``; empty when it cannot be read."""
    try:
        if os.name == "nt":
            import ctypes

            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                return buffer.value
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLocale"],
                capture_output=True, text=True, timeout=2,
            )
            if result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(name, "").split(":", 1)[0]
        if value and value not in ("C", "POSIX"):
            return value
    return ""


def resolve_language(preference=None, environ=None):
    """The language to show: the user's choice, then the launcher's, then the OS locale."""
    environ = os.environ if environ is None else environ
    for candidate in (preference, environ.get("PYAPPIFY_LOCALE")):
        language = match_language(candidate)
        if language:
            return language
    return language_from_locale(system_locale())


def t(key, language=EN, **values):
    """The text for ``key`` in ``language`` (English if missing), formatted with ``values``."""
    texts = STRINGS.get(key)
    if texts is None:
        return key
    index = LANGUAGES.index(language) if language in LANGUAGES else 0
    text = texts[index] or texts[0]
    return text.format(**values) if values else text


# Each entry lists the text in the order of LANGUAGES:
# en, zh-CN, zh-TW, es, ja, ko.
STRINGS = {
    "window_title": (
        "{app} — Updates", "{app} — 更新", "{app} — 更新",
        "{app} — Actualizaciones", "{app} — アップデート", "{app} — 업데이트",
    ),
    "app": ("App", "应用", "應用程式", "Aplicación", "アプリ", "앱"),
    "language": ("Language", "语言", "語言", "Idioma", "言語", "언어"),
    "theme_system": ("System", "跟随系统", "跟隨系統", "Sistema", "システム", "시스템"),
    "theme_light": ("Light", "浅色", "淺色", "Claro", "ライト", "라이트"),
    "theme_dark": ("Dark", "深色", "深色", "Oscuro", "ダーク", "다크"),
    "installed_version": (
        "Installed: {version}", "已安装：{version}", "已安裝：{version}",
        "Instalada: {version}", "インストール済み: {version}", "설치됨: {version}",
    ),
    "untagged_commit": (
        "an untagged commit", "未标记版本的提交", "未標記版本的提交",
        "un commit sin etiqueta", "タグのないコミット", "태그 없는 커밋",
    ),
    "looking_for_app": (
        "Looking for the app…", "正在查找应用…", "正在尋找應用程式…",
        "Buscando la aplicación…", "アプリを探しています…", "앱을 찾는 중…",
    ),
    "opening_repository": (
        "Opening the repository…", "正在打开仓库…", "正在開啟儲存庫…",
        "Abriendo el repositorio…", "リポジトリを開いています…", "저장소를 여는 중…",
    ),
    "cannot_read_repository": (
        "Cannot read the app's repository", "无法读取应用的仓库", "無法讀取應用程式的儲存庫",
        "No se puede leer el repositorio de la aplicación", "アプリのリポジトリを読み込めません",
        "앱 저장소를 읽을 수 없습니다",
    ),
    "versions": ("Versions", "版本", "版本", "Versiones", "バージョン", "버전"),
    "releases": ("Releases", "正式版", "正式版", "Estables", "リリース", "정식 버전"),
    "all": ("All", "全部", "全部", "Todas", "すべて", "전체"),
    "column_version": ("VERSION", "版本", "版本", "VERSIÓN", "バージョン", "버전"),
    "column_type": ("TYPE", "类型", "類型", "TIPO", "種類", "유형"),
    "column_status": ("STATUS", "状态", "狀態", "ESTADO", "状態", "상태"),
    "kind_release": ("Release", "正式版", "正式版", "Estable", "リリース", "정식"),
    "kind_prerelease": ("Pre-release", "预览版", "預覽版", "Preliminar", "プレリリース", "사전 출시"),
    "kind_branch": ("Branch", "分支", "分支", "Rama", "ブランチ", "브랜치"),
    "kind_local": ("Local branch", "本地分支", "本機分支", "Rama local", "ローカルブランチ", "로컬 브랜치"),
    "kind_pr": ("Pull request", "拉取请求", "拉取請求", "Pull request", "プルリクエスト", "풀 리퀘스트"),
    "relation_current": ("✓ Installed", "✓ 已安装", "✓ 已安裝", "✓ Instalada", "✓ インストール済み", "✓ 설치됨"),
    "relation_newer": ("↑ Newer", "↑ 较新", "↑ 較新", "↑ Más nueva", "↑ 新しい", "↑ 최신"),
    "relation_older": ("↓ Older", "↓ 较旧", "↓ 較舊", "↓ Más antigua", "↓ 古い", "↓ 이전"),
    "relation_other": ("⇄ Other", "⇄ 其他", "⇄ 其他", "⇄ Otra", "⇄ その他", "⇄ 기타"),
    "chip_installed": ("Installed", "已安装", "已安裝", "Instalada", "インストール済み", "설치됨"),
    "chip_newer": ("Newer", "较新", "較新", "Más nueva", "新しい", "최신"),
    "chip_older": ("Older", "较旧", "較舊", "Más antigua", "古い", "이전"),
    "checking_for_updates": (
        "Checking for updates…", "正在检查更新…", "正在檢查更新…",
        "Buscando actualizaciones…", "アップデートを確認しています…", "업데이트 확인 중…",
    ),
    "newer_available": (
        "Newer versions available: {count}", "可用的新版本：{count}", "可用的新版本：{count}",
        "Versiones nuevas disponibles: {count}", "新しいバージョン: {count} 件",
        "새 버전 {count}개 사용 가능",
    ),
    "up_to_date": (
        "You're up to date.", "已是最新版本。", "已是最新版本。",
        "Ya tienes la última versión.", "最新の状態です。", "최신 상태입니다.",
    ),
    "check_failed": (
        "Could not check for updates", "无法检查更新", "無法檢查更新",
        "No se pudo buscar actualizaciones", "アップデートを確認できませんでした",
        "업데이트를 확인할 수 없습니다",
    ),
    "select_version": (
        "Select a version to see what changed.", "选择一个版本以查看更新内容。",
        "選擇一個版本以查看更新內容。", "Selecciona una versión para ver los cambios.",
        "バージョンを選ぶと変更点が表示されます。", "버전을 선택하면 변경 사항이 표시됩니다.",
    ),
    "meta_commit": ("commit {commit}", "提交 {commit}", "提交 {commit}", "commit {commit}",
                    "コミット {commit}", "커밋 {commit}"),
    "meta_previous": ("previous {version}", "上一版 {version}", "上一版 {version}",
                      "anterior {version}", "前回 {version}", "이전 {version}"),
    "changes_since": (
        "Changes since {version}", "自 {version} 以来的更新", "自 {version} 以來的更新",
        "Cambios desde {version}", "{version} からの変更点", "{version} 이후 변경 사항",
    ),
    "whats_in_version": (
        "What's in this version", "此版本的内容", "此版本的內容",
        "Novedades de esta versión", "このバージョンの内容", "이 버전의 내용",
    ),
    "changes_vs_installed": (
        "Changes compared to the installed version", "与已安装版本相比的更新",
        "與已安裝版本相比的更新", "Cambios respecto a la versión instalada",
        "インストール済みバージョンからの変更点", "설치된 버전 대비 변경 사항",
    ),
    "no_notes": (
        "No patch notes for this version.", "此版本没有更新说明。", "此版本沒有更新說明。",
        "Esta versión no tiene notas.", "このバージョンには更新内容の記載がありません。",
        "이 버전에는 패치 노트가 없습니다.",
    ),
    "update": ("Update", "更新", "更新", "Actualizar", "アップデート", "업데이트"),
    "update_to": ("Update to {version}", "更新到 {version}", "更新至 {version}",
                  "Actualizar a {version}", "{version} にアップデート", "{version}(으)로 업데이트"),
    "downgrade_to": ("Downgrade to {version}", "降级到 {version}", "降級至 {version}",
                     "Volver a {version}", "{version} にダウングレード", "{version}(으)로 다운그레이드"),
    "switch_to": ("Switch to {version}", "切换到 {version}", "切換至 {version}",
                  "Cambiar a {version}", "{version} に切り替え", "{version}(으)로 전환"),
    "is_installed": ("{version} is installed", "已安装 {version}", "已安裝 {version}",
                     "{version} está instalada", "{version} はインストール済みです",
                     "{version} 설치됨"),
    "mirror_title": ("Pip mirror", "Pip 镜像源", "Pip 鏡像來源", "Espejo de pip", "pip ミラー", "pip 미러"),
    "mirror_hint": (
        "Where updates download Python packages from.", "更新时从这里下载 Python 包。",
        "更新時從這裡下載 Python 套件。", "Desde dónde las actualizaciones descargan paquetes de Python.",
        "アップデート時に Python パッケージを取得する場所です。",
        "업데이트 시 Python 패키지를 내려받는 곳입니다.",
    ),
    "mirror_saved": ("✓ Saved", "✓ 已保存", "✓ 已儲存", "✓ Guardado", "✓ 保存しました", "✓ 저장됨"),
    "mirror_failed": (
        "Could not save the pip mirror", "无法保存 pip 镜像源", "無法儲存 pip 鏡像來源",
        "No se pudo guardar el espejo de pip", "pip ミラーを保存できませんでした",
        "pip 미러를 저장할 수 없습니다",
    ),
    "mirror_default": (
        "Default (pip configuration)", "默认（pip 配置）", "預設（pip 設定）",
        "Predeterminado (configuración de pip)", "既定 (pip の設定)", "기본값 (pip 설정)",
    ),
    "mirror_pypi": ("PyPI (official)", "PyPI（官方）", "PyPI（官方）", "PyPI (oficial)",
                    "PyPI (公式)", "PyPI (공식)"),
    "mirror_tuna": ("Tsinghua University (TUNA)", "清华大学（TUNA）", "清華大學（TUNA）",
                    "Universidad Tsinghua (TUNA)", "清華大学 (TUNA)", "칭화대학교 (TUNA)"),
    "mirror_aliyun": ("Alibaba Cloud", "阿里云", "阿里雲", "Alibaba Cloud", "Alibaba Cloud",
                      "Alibaba Cloud"),
    "mirror_ustc": ("USTC", "中国科学技术大学", "中國科學技術大學", "USTC", "USTC", "USTC"),
    "mirror_huawei": ("Huawei Cloud", "华为云", "華為雲", "Huawei Cloud", "Huawei Cloud",
                      "Huawei Cloud"),
    "mirror_tencent": ("Tencent Cloud", "腾讯云", "騰訊雲", "Tencent Cloud", "Tencent Cloud",
                       "Tencent Cloud"),
    "log": ("Log", "日志", "日誌", "Registro", "ログ", "로그"),
    "copy": ("Copy", "复制", "複製", "Copiar", "コピー", "복사"),
    "open_log_file": ("Open log file", "打开日志文件", "開啟日誌檔", "Abrir archivo de registro",
                      "ログファイルを開く", "로그 파일 열기"),
    "issues": ("Issues: {count}", "问题：{count}", "問題：{count}", "Problemas: {count}",
               "問題: {count}", "문제: {count}"),
    "log_copied": (
        "Log copied to the clipboard.", "日志已复制到剪贴板。", "日誌已複製到剪貼簿。",
        "Registro copiado al portapapeles.", "ログをクリップボードにコピーしました。",
        "로그를 클립보드에 복사했습니다.",
    ),
    "no_log": (
        "No update log has been written yet.", "还没有更新日志。", "尚未產生更新日誌。",
        "Todavía no hay registro de actualización.", "アップデートログはまだありません。",
        "아직 업데이트 로그가 없습니다.",
    ),
    "something_wrong": (
        "Something went wrong. See the log for details.", "出现问题，详情请查看日志。",
        "發生問題，詳情請查看日誌。", "Algo salió mal. Consulta el registro.",
        "問題が発生しました。詳しくはログを確認してください。",
        "문제가 발생했습니다. 자세한 내용은 로그를 확인하세요.",
    ),
    "confirm_title": ("Update {app}", "更新 {app}", "更新 {app}", "Actualizar {app}",
                      "{app} のアップデート", "{app} 업데이트"),
    "confirm_body": (
        "{app} will close, update to {version} and start again.",
        "{app} 将关闭，更新到 {version} 后重新启动。",
        "{app} 將關閉，更新至 {version} 後重新啟動。",
        "{app} se cerrará, se actualizará a {version} y se volverá a abrir.",
        "{app} を終了し、{version} にアップデートしてから再起動します。",
        "{app}이(가) 종료되고 {version}(으)로 업데이트한 뒤 다시 시작됩니다.",
    ),
    "step_prepare": ("Download update", "下载更新", "下載更新", "Descargar", "ダウンロード", "다운로드"),
    "step_stop": ("Close the app", "关闭应用", "關閉應用程式", "Cerrar la app", "アプリを終了", "앱 종료"),
    "step_checkout": ("Apply the new files", "应用新文件", "套用新檔案", "Aplicar archivos",
                      "ファイルを適用", "새 파일 적용"),
    "step_dependencies": ("Install dependencies", "安装依赖", "安裝相依套件", "Instalar dependencias",
                          "依存関係をインストール", "종속성 설치"),
    "step_restart": ("Restart the app", "重启应用", "重新啟動應用程式", "Reiniciar la app",
                     "アプリを再起動", "앱 다시 시작"),
    "step_rollback": ("Roll back", "回滚", "還原", "Revertir", "ロールバック", "롤백"),
    "detail_prepare": ("Fetching {version}", "正在获取 {version}", "正在取得 {version}",
                       "Descargando {version}", "{version} を取得しています", "{version} 가져오는 중"),
    "detail_stop": ("Waiting for the app to close", "正在等待应用关闭", "正在等待應用程式關閉",
                    "Esperando a que se cierre la app", "アプリの終了を待っています",
                    "앱이 종료되기를 기다리는 중"),
    "detail_checkout": ("Checking out {version}", "正在切换到 {version}", "正在切換至 {version}",
                        "Aplicando {version}", "{version} を展開しています", "{version} 적용 중"),
    "detail_dependencies": ("Running pip install", "正在运行 pip install", "正在執行 pip install",
                            "Ejecutando pip install", "pip install を実行しています",
                            "pip install 실행 중"),
    "detail_restart": ("Starting the app", "正在启动应用", "正在啟動應用程式", "Iniciando la app",
                       "アプリを起動しています", "앱을 시작하는 중"),
    "detail_rollback": ("Restoring the previous version", "正在恢复之前的版本", "正在還原先前的版本",
                        "Restaurando la versión anterior", "以前のバージョンに戻しています",
                        "이전 버전으로 복원하는 중"),
    "changes_to_apply": ("Changes to apply: {count}", "待应用的更改：{count}", "待套用的變更：{count}",
                         "Cambios por aplicar: {count}", "適用する変更: {count} 件",
                         "적용할 변경 사항: {count}개"),
    "updating_to": ("Updating to {version}", "正在更新到 {version}", "正在更新至 {version}",
                    "Actualizando a {version}", "{version} にアップデートしています",
                    "{version}(으)로 업데이트하는 중"),
    "from_version": ("From {version}", "当前版本 {version}", "目前版本 {version}", "Desde {version}",
                     "現在のバージョン: {version}", "현재 버전 {version}"),
    "keep_window_open": (
        "Keep this window open until it finishes.", "完成前请不要关闭此窗口。",
        "完成前請不要關閉此視窗。", "Mantén esta ventana abierta hasta que termine.",
        "完了するまでこのウィンドウを閉じないでください。",
        "완료될 때까지 이 창을 닫지 마세요.",
    ),
    "updating_status": (
        "Updating… Keep this window open.", "正在更新…请不要关闭此窗口。",
        "正在更新…請不要關閉此視窗。", "Actualizando… Mantén esta ventana abierta.",
        "アップデート中… このウィンドウを閉じないでください。",
        "업데이트 중… 이 창을 닫지 마세요.",
    ),
    "updated_to": ("Updated to {version}", "已更新到 {version}", "已更新至 {version}",
                   "Actualizada a {version}", "{version} にアップデートしました",
                   "{version}(으)로 업데이트됨"),
    "app_restarting": (
        "The app is starting on the new version.", "应用正在以新版本启动。",
        "應用程式正在以新版本啟動。", "La app se está iniciando con la nueva versión.",
        "新しいバージョンでアプリを起動しています。", "새 버전으로 앱을 시작하는 중입니다.",
    ),
    "start_app_again": (
        "Start the app again to use the new version.", "请重新启动应用以使用新版本。",
        "請重新啟動應用程式以使用新版本。", "Vuelve a abrir la app para usar la nueva versión.",
        "新しいバージョンを使うにはアプリを再起動してください。",
        "새 버전을 사용하려면 앱을 다시 시작하세요.",
    ),
    "close": ("Close", "关闭", "關閉", "Cerrar", "閉じる", "닫기"),
    "keep_open": ("Keep open", "保持打开", "保持開啟", "Mantener abierta", "開いたままにする", "열어 두기"),
    "closing_in": ("Closing in {seconds}s…", "{seconds} 秒后关闭…", "{seconds} 秒後關閉…",
                   "Se cerrará en {seconds} s…", "{seconds} 秒後に閉じます…",
                   "{seconds}초 후 닫힘…"),
    "update_complete": ("Update complete.", "更新完成。", "更新完成。", "Actualización completada.",
                        "アップデートが完了しました。", "업데이트가 완료되었습니다."),
    "update_failed_to": (
        "Could not update to {version}", "无法更新到 {version}", "無法更新至 {version}",
        "No se pudo actualizar a {version}", "{version} にアップデートできませんでした",
        "{version}(으)로 업데이트할 수 없습니다",
    ),
    "previous_restored": (
        "Your previous version was restored.", "已恢复到之前的版本。", "已還原至先前的版本。",
        "Se restauró la versión anterior.", "以前のバージョンに戻しました。",
        "이전 버전으로 복원되었습니다.",
    ),
    "nothing_changed": ("Nothing was changed.", "未做任何更改。", "未做任何變更。",
                        "No se cambió nada.", "何も変更されていません。", "변경된 내용이 없습니다."),
    "check_log_below": ("Check the log below.", "请查看下方日志。", "請查看下方日誌。",
                        "Consulta el registro de abajo.", "下のログを確認してください。",
                        "아래 로그를 확인하세요."),
    "update_failed": ("The update failed", "更新失败", "更新失敗", "La actualización falló",
                      "アップデートに失敗しました", "업데이트에 실패했습니다"),
    "see_log": ("See the log for details.", "详情请查看日志。", "詳情請查看日誌。",
                "Consulta el registro para más detalles.", "詳しくはログを確認してください。",
                "자세한 내용은 로그를 확인하세요."),
    "back_to_versions": ("Back to versions", "返回版本列表", "返回版本清單", "Volver a las versiones",
                         "バージョン一覧に戻る", "버전 목록으로"),
    "in_progress_title": ("Update in progress", "正在更新", "正在更新", "Actualización en curso",
                          "アップデート中", "업데이트 진행 중"),
    "in_progress_body": (
        "Please wait until the update finishes. Closing now could leave the app half updated.",
        "请等待更新完成。现在关闭可能导致应用只更新了一部分。",
        "請等待更新完成。現在關閉可能導致應用程式只更新了一部分。",
        "Espera a que termine la actualización. Cerrar ahora podría dejar la app a medio actualizar.",
        "アップデートが終わるまでお待ちください。今閉じるとアプリが中途半端な状態になる可能性があります。",
        "업데이트가 끝날 때까지 기다려 주세요. 지금 닫으면 앱이 일부만 업데이트될 수 있습니다.",
    ),
}
