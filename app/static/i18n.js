/* Stellar Data Exporter English/Korean browser-side localization.
 * This file translates presentation text only, never form values or query/code data.
 * UI text is translated on demand so existing asynchronous controls keep working.
 */
(() => {
  "use strict";

  const STORAGE_KEY = "stellarDataExporter.uiLanguage.v1";
  const korean = new Map([
    ["User Scope uses the API Key directly to obtain a short-lived JWT. Raw-data query and export use Stellar Cyber Query (Lucene); Elasticsearch DSL API queries are Root Scope only.", "User Scope는 API Key로 단기 JWT를 발급받습니다. 원본 데이터 조회와 내보내기는 Stellar Cyber Query(Lucene)를 사용하며, Elasticsearch DSL API는 Root Scope에서만 지원됩니다."],
    ["Root Scope uses account email + All-Access Token. JWT refresh is automatic during long exports, and Elasticsearch DSL is available.", "Root Scope는 계정 이메일과 All-Access Token을 사용합니다. 장시간 내보내기 중 JWT가 자동 갱신되며 Elasticsearch DSL을 사용할 수 있습니다."],
    ["At least one data source is required. Select another source before removing this one.", "데이터 소스를 하나 이상 선택해야 합니다. 현재 소스를 제거하려면 먼저 다른 소스를 선택하세요."],
    ["Preparing the browser download on the server… Settings remain locked to this job.", "서버에서 브라우저 다운로드 파일을 준비하는 중… 이 작업이 끝날 때까지 설정이 잠깁니다."],
    ["Settings locked. Validating the selected export settings…", "설정을 잠갔습니다. 선택한 내보내기 설정을 검증하는 중…"],
    ["Session connection restored.", "세션 연결이 복원됐습니다."],
    ["No connection saved for this session.", "이 세션에 저장된 연결정보가 없습니다."],
    ["Copy completed.", "복사 완료."],
    ["Security events and alerts", "보안 이벤트 및 경고"],
    ["Assets", "자산(Assets)"],
    ["Asset inventory and analytics data", "자산 목록 및 분석 데이터"],
    ["AWS Events", "AWS 이벤트"],
    ["AWS CloudTrail and related event data", "AWS CloudTrail 및 관련 이벤트 데이터"],
    ["IDPS / Malware Sandbox", "IDPS / 악성코드 샌드박스"],
    ["IDPS, firewall threat, and malware sandbox events", "IDPS, 방화벽 위협 및 악성코드 샌드박스 이벤트"],
    ["Linux Events", "Linux 이벤트"],
    ["Linux audit and server-sensor events", "Linux 감사 및 서버 센서 이벤트"],
    ["Scans", "스캔(Scans)"],
    ["Vulnerability and scan data", "취약점 및 스캔 데이터"],
    ["Sensor Monitoring", "센서 모니터링"],
    ["Sensor statistics and monitoring data", "센서 통계 및 모니터링 데이터"],
    ["Signals", "시그널(Signals)"],
    ["Contextual signals used for threat hunting", "위협 헌팅에 사용하는 상황별 시그널"],
    ["Syslog", "Syslog 로그"],
    ["Application and device logs from log forwarders", "로그 포워더를 통해 수집한 애플리케이션 및 장비 로그"],
    ["Traffic", "네트워크 트래픽(Traffic)"],
    ["Network flow and traffic metadata", "네트워크 흐름 및 트래픽 메타데이터"],
    ["Users", "사용자(Users)"],
    ["User analytics and identity data", "사용자 분석 및 ID 데이터"],
    ["Windows Events", "Windows 이벤트"],
    ["Windows event logs and Windows server-sensor events", "Windows 이벤트 로그 및 Windows 서버 센서 이벤트"],
    ["Wildcard fallback", "와일드카드 대체 패턴"],
    ["Date-scoped", "날짜 범위 적용"],
    ["All indices", "모든 인덱스"],
    ["Static pattern", "고정 패턴"],
    ["Known mapping", "확인된 매핑"],
    ["Data Exporter", "데이터 내보내기"],
    ["Query & Export Utility", "조회 및 내보내기 도구"],
    ["Interface mode", "인터페이스 모드"],
    ["Language", "언어"],
    ["Basic", "기본"],
    ["Advanced", "고급"],
    ["Browser-session connection", "브라우저 세션 연결"],
    ["STELLAR CYBER · DATA EXPORT", "STELLAR CYBER · 데이터 내보내기"],
    ["Query once. Export safely at scale.", "간편하게 조회하고, 대용량 데이터도 안전하게 내보내세요."],
    ["Choose data, time, query, output and destination. Safe defaults handle the rest; advanced tuning is available when needed.", "데이터 소스, 시간, 검색 조건, 출력 형식과 대상을 선택하세요. 기본 설정만으로 실행할 수 있으며, 필요할 때 고급 옵션을 사용할 수 있습니다."],
    ["service ready", "서비스 준비 완료"],
    ["Choose the credential type you were issued. Save the complete connection securely if you want to reuse it on the next visit.", "발급받은 인증정보 유형을 선택하세요. 필요하면 현재 브라우저 세션에 연결정보를 임시로 저장할 수 있습니다."],
    ["Root Scope", "Root Scope(루트 범위)"],
    ["User Scope", "User Scope(사용자 범위)"],
    ["Account email + All-Access Token.", "계정 이메일 + All-Access Token"],
    ["User API Key for raw-data query and export.", "원본 데이터 조회 및 내보내기용 사용자 API Key"],
    ["Host", "호스트"],
    ["Account email", "계정 이메일"],
    ["All-Access Token", "All-Access Token"],
    ["User API Key", "사용자 API Key"],
    ["Enter Root Scope All-Access Token", "Root Scope All-Access Token 입력"],
    ["Enter User Scope API Key", "User Scope API Key 입력"],
    ["Root Scope uses account email + All-Access Token. JWT refresh is automatic during long exports.", "Root Scope는 계정 이메일과 All-Access Token을 사용합니다. 장시간 내보내기 중 JWT는 자동 갱신됩니다."],
    ["User Scope uses a User API Key. It can query and export raw data using Stellar Cyber Query (Lucene).", "User Scope는 사용자 API Key를 사용하며 Stellar Cyber Query(Lucene)로 원본 데이터를 조회하고 내보냅니다."],
    ["Verify TLS certificate", "TLS 인증서 검증"],
    ["Secure TLS verification is enabled by default.", "안전을 위해 TLS 인증서 검증이 기본 활성화되어 있습니다."],
    ["Test connection", "연결 테스트"],
    ["Tenant", "테넌트"],
    ["Required", "필수"],
    ["Connect first, then choose exactly one tenant. Preview, count, export, resume and schedules are server-side restricted to this tenant.", "먼저 연결한 뒤 테넌트 하나를 선택하세요. 미리보기, 건수 조회, 내보내기, 재개 및 예약 작업은 해당 테넌트로 제한됩니다."],
    ["Test connection to load tenants", "연결 테스트를 실행하여 테넌트 불러오기"],
    ["Temporary connection memory", "임시 연결정보 저장"],
    ["Remember Host, credential, and the selected tenant only in the current browser session. On reload, the tenant is revalidated and restored automatically. Forget session immediately clears them from this page.", "호스트, 인증정보, 선택한 테넌트를 현재 브라우저 세션에만 저장합니다. 새로고침 시 테넌트 접근 권한을 재확인한 뒤 복원합니다. 세션 지우기를 누르면 즉시 삭제됩니다."],
    ["Forget session", "세션 지우기"],
    ["Remember this session", "이 세션에 저장"],
    ["Query", "쿼리"],
    ["Paste a query you wrote yourself or generated with any AI tool.", "직접 작성하거나 AI 도구로 생성한 쿼리를 붙여넣으세요."],
    ["Saved export profiles", "저장한 내보내기 프로필"],
    ["Browser-only settings. Credentials and private keys are never saved.", "설정은 브라우저에만 저장됩니다. 인증정보와 개인키는 저장되지 않습니다."],
    ["Profile name", "프로필 이름"],
    ["No saved profiles", "저장된 프로필 없음"],
    ["Save", "저장"],
    ["Load", "불러오기"],
    ["Delete", "삭제"],
    ["Query history & favorites", "쿼리 기록 및 즐겨찾기"],
    ["Successful previews are kept locally so common queries can be reused.", "미리보기에 성공한 쿼리를 이 브라우저에 저장하여 다시 사용할 수 있습니다."],
    ["No query history", "쿼리 기록 없음"],
    ["Favorite", "즐겨찾기"],
    ["Unfavorite", "즐겨찾기 해제"],
    ["Clear", "지우기"],
    ["Data sources", "데이터 소스"],
    ["At least one data source must remain selected. Alerts is selected by default. Internal index names are mapped automatically.", "데이터 소스를 하나 이상 선택해야 합니다. Alerts가 기본 선택되며 내부 인덱스 이름은 자동 매핑됩니다."],
    ["Select all", "전체 선택"],
    ["Alerts only", "Alerts만 선택"],
    ["Loading data sources…", "데이터 소스 불러오는 중…"],
    ["Time field", "시간 필드"],
    ["Selected", "선택됨"],
    ["Resolved indices", "조회 대상 인덱스"],
    ["Date-scoped automatically when Stellar Cyber documents a safe daily pattern", "공식 일별 인덱스 패턴을 확인한 경우 자동으로 날짜 범위 적용"],
    ["Show actual indices", "실제 인덱스 표시"],
    ["Hide actual indices", "실제 인덱스 숨기기"],
    ["Planning selected data sources…", "선택한 데이터 소스 분석 중…"],
    ["Planning…", "분석 중…"],
    ["Relative time", "상대 시간"],
    ["minutes", "분"],
    ["hours", "시간"],
    ["days", "일"],
    ["Apply", "적용"],
    ["Start", "시작"],
    ["End", "종료"],
    ["Query filter", "쿼리 필터"],
    ["Editable", "편집 가능"],
    ["Use Elasticsearch DSL or paste a Stellar Cyber Lucene query. The selected time range is managed automatically.", "Elasticsearch DSL 또는 Stellar Cyber Lucene 쿼리를 입력하세요. 선택한 시간 범위는 자동으로 반영됩니다."],
    ["Elasticsearch DSL", "Elasticsearch DSL"],
    ["Root Scope only. JSON query body for advanced control.", "Root Scope 전용 · 고급 JSON 쿼리"],
    ["Stellar Cyber Query", "Stellar Cyber 쿼리"],
    ["Lucene syntax used by Stellar Cyber Search and Query Builder.", "Stellar Cyber 검색 및 Query Builder에서 사용하는 Lucene 문법"],
    ["Root Scope only.", "Root Scope 전용."],
    ["Elasticsearch DSL is available with Account Email + All-Access Token. User Scope API Keys use Stellar Cyber Query (Lucene).", "Elasticsearch DSL은 계정 이메일과 All-Access Token을 사용하는 Root Scope에서만 지원됩니다. User Scope API Key는 Stellar Cyber Query(Lucene)를 사용합니다."],
    ["Examples:", "예시:"],
    ["Query Inspector", "쿼리 검사기"],
    ["Final request, query statistics, and export plan", "실제 요청, 쿼리 통계 및 내보내기 계획"],
    ["Read only", "읽기 전용"],
    ["Copy tools", "복사 도구"],
    ["Use these when you want to inspect or reproduce the exact request outside this UI. Credentials are not copied.", "이 화면 밖에서 동일한 요청을 확인하거나 재현할 때 사용합니다. 인증정보는 복사하지 않습니다."],
    ["Copy DSL", "DSL 복사"],
    ["Copies the final query JSON after the exporter adds managed tenant and time filters. Useful for reviewing the exact query logic.", "테넌트 및 시간 필터가 적용된 최종 JSON 쿼리를 복사합니다."],
    ["Copy request path", "요청 경로 복사"],
    ["Copies only the Stellar Cyber API path and resolved index pattern. Useful when building scripts or checking API endpoints.", "스크립트 작성이나 API 확인을 위해 Stellar Cyber API 경로와 인덱스 패턴만 복사합니다."],
    ["Copy cURL", "cURL 복사"],
    ["Copies a terminal-ready cURL example so you can reproduce the request outside the UI. Tokens and credentials stay redacted.", "터미널에서 실행할 수 있는 cURL 예시를 복사합니다. 토큰과 인증정보는 마스킹됩니다."],
    ["Request", "요청"],
    ["Method", "메서드"],
    ["Final endpoint", "최종 엔드포인트"],
    ["Request path", "요청 경로"],
    ["Statistics", "통계"],
    ["Matched records", "일치하는 레코드"],
    ["Preview required", "미리보기 필요"],
    ["Preview latency", "미리보기 응답 시간"],
    ["Preview bytes", "미리보기 크기"],
    ["Estimated output size", "예상 출력 크기"],
    ["Export Plan", "내보내기 계획"],
    ["Selected fields", "선택한 필드"],
    ["All source fields", "모든 원본 필드"],
    ["Export limit", "내보내기 건수 제한"],
    ["All matching records", "일치하는 모든 레코드"],
    ["Adaptive slicing", "적응형 분할 조회"],
    ["Enabled", "활성화"],
    ["Enabled · source/day partition + target+1 probe", "활성화 · 소스/일 단위 분할 및 목표+1 탐색"],
    ["Target records/query", "쿼리당 목표 건수"],
    ["Estimated slices", "예상 조회 구간"],
    ["Max file size", "최대 파일 크기"],
    ["No split", "파일 분할 없음"],
    ["Estimated output files", "예상 출력 파일 수"],
    ["Overlap policy", "중복 범위 정책"],
    ["Allow overlap", "범위 중복 허용"],
    ["Ready to validate.", "검증 준비 완료"],
    ["Validate JSON", "JSON 검증"],
    ["Validate Query", "쿼리 검증"],
    ["Preview 100 records", "100건 미리보기"],
    ["Preview", "미리보기"],
    ["Preview before starting a large export.", "대용량 내보내기 전에 미리보기를 실행하세요."],
    ["Estimated size", "예상 크기"],
    ["Query time", "쿼리 실행 시간"],
    ["Run Preview to inspect data", "미리보기를 실행하여 데이터 확인"],
    ["No data loaded yet.", "아직 불러온 데이터가 없습니다."],
    ["Export fields", "내보낼 필드"],
    ["Choose fields discovered in Preview. Selected order becomes the CSV column order.", "미리보기에서 찾은 필드를 선택하세요. 선택 순서는 CSV 열 순서가 됩니다."],
    ["Search fields…", "필드 검색…"],
    ["Nested fields use dot notation. Use ↑/↓ to change export order.", "중첩 필드는 점(.) 표기법을 사용합니다. ↑/↓로 내보내기 순서를 변경하세요."],
    ["Output", "출력 형식"],
    ["Choose CSV or JSON. Advanced mode adds field, limit, compression and file-splitting controls.", "CSV 또는 JSON을 선택하세요. 고급 모드에서는 필드, 건수 제한, 압축 및 파일 분할을 설정할 수 있습니다."],
    ["Spreadsheet-friendly tabular export.", "스프레드시트에 적합한 표 형식"],
    ["JSON Array", "JSON 배열"],
    ["Streams one valid JSON array.", "유효한 JSON 배열 하나로 출력"],
    ["One JSON object per line.", "한 줄에 JSON 객체 하나씩 출력"],
    ["Delimiter", "구분자"],
    ["Comma (,)", "쉼표 (,)"],
    ["Semicolon (;)", "세미콜론 (;)"],
    ["Tab", "탭"],
    ["Pipe (|)", "파이프 (|)"],
    ["Include header row", "헤더 행 포함"],
    ["UTF-8 BOM for Excel", "Excel용 UTF-8 BOM"],
    ["Flatten nested objects to dot notation", "중첩 객체를 점(.) 표기법으로 펼치기"],
    ["Export records", "내보낼 레코드"],
    ["Limit to", "최대 건수"],
    ["Filename", "파일 이름"],
    ["gzip compression", "gzip 압축"],
    ["Split output by file size", "파일 크기 기준 분할"],
    ["Generated files", "생성되는 파일"],
    ["Parts are split on record boundaries, so a file may slightly exceed the target size. Browser downloads with multiple parts are bundled into one ZIP.", "레코드 단위로 파일을 분할하므로 지정 크기를 약간 초과할 수 있습니다. 브라우저로 여러 파일을 받는 경우 하나의 ZIP으로 묶입니다."],
    ["Destination", "전송 대상"],
    ["Choose a direct browser download, S3-compatible object storage, or SFTP.", "브라우저 직접 다운로드, S3 호환 스토리지 또는 SFTP를 선택하세요."],
    ["Download", "다운로드"],
    ["Stream directly to this browser", "현재 브라우저로 직접 다운로드"],
    ["S3-compatible", "S3 호환"],
    ["SSH key or password", "SSH 키 또는 비밀번호"],
    ["Endpoint URL", "엔드포인트 URL"],
    ["Blank for AWS S3", "AWS S3를 사용하면 비워두세요"],
    ["Region", "리전"],
    ["Bucket", "버킷"],
    ["Prefix", "접두 경로"],
    ["Access key", "액세스 키"],
    ["Secret key", "비밀 키"],
    ["Force path-style addressing", "경로 스타일 주소 강제"],
    ["Test destination", "전송 대상 테스트"],
    ["Port", "포트"],
    ["Username", "사용자 이름"],
    ["Remote directory", "원격 디렉터리"],
    ["Authentication", "인증 방식"],
    ["SSH private key", "SSH 개인키"],
    ["Password", "비밀번호"],
    ["Private key", "개인키"],
    ["Verify SSH host key", "SSH 호스트 키 검증"],
    ["Recommended", "권장"],
    ["Get host key", "호스트 키 가져오기"],
    ["For a new SFTP server, fetch its SSH host key, compare the SHA256 fingerprint with the server administrator, then trust that key before testing the destination.", "새 SFTP 서버에서는 SSH 호스트 키를 가져온 뒤 SHA256 지문을 서버 관리자와 비교하고, 신뢰할 키로 등록한 다음 전송 대상 테스트를 진행하세요."],
    ["Algorithm", "알고리즘"],
    ["SHA256 fingerprint", "SHA256 지문"],
    ["Trust this host key", "이 호스트 키 신뢰"],
    ["Host-key verification is separate from password/private-key authentication.", "호스트 키 검증은 비밀번호/개인키 인증과 별도로 진행됩니다."],
    ["Adaptive export settings", "적응형 내보내기 설정"],
    ["Target records / slice", "분할 구간당 목표 건수"],
    ["Minimum slice (ms)", "최소 분할 구간(ms)"],
    ["Allow overlapping matching exports", "조건이 같은 내보내기 범위 중복 허용"],
    ["Reject overlapping matching exports", "조건이 같은 내보내기 범위 중복 거부"],
    ["Large exports are first partitioned by data source and into windows of at most 24 hours. Each partition uses lightweight target+1 probes without repeated exact counts; oversized or slow responses are bisected into smaller half-open time slices. Reject overlap blocks matching export pipelines whose requested time windows intersect; adjacent ranges are allowed.", "대용량 데이터는 데이터 소스별 최대 24시간 단위로 나누어 조회합니다. 각 구간은 가벼운 탐색 요청으로 크기를 확인하고, 너무 크거나 느리면 더 작은 시간 구간으로 다시 분할합니다. 중복 거부를 선택하면 같은 조건의 겹치는 시간 범위를 차단하지만, 이어지는 구간은 허용합니다."],
    ["Scheduled Export", "예약 내보내기"],
    ["Optional", "선택"],
    ["Run the current query/output configuration repeatedly to S3 or SFTP.", "현재 쿼리와 출력 설정을 사용해 S3 또는 SFTP로 정기적으로 전송합니다."],
    ["Refresh", "새로고침"],
    ["Schedule name", "예약 이름"],
    ["Run every", "실행 주기"],
    ["First-run lookback window", "첫 실행 조회 범위"],
    ["Enabled after save", "저장 후 활성화"],
    ["Schedules require S3/SFTP. Query and credentials are encrypted at rest; scheduled runs always reject matching overlap and continue from the last successful window.", "예약 내보내기는 S3/SFTP만 지원합니다. 쿼리와 인증정보는 암호화 저장되며, 동일 조건의 중복 작업을 차단하고 마지막 성공 구간부터 이어서 실행합니다."],
    ["Save schedule", "예약 저장"],
    ["Name", "이름"],
    ["Cadence", "실행 간격"],
    ["Window", "조회 구간"],
    ["Next", "다음 실행"],
    ["Last status", "마지막 상태"],
    ["Actions", "작업"],
    ["Loading schedules…", "예약 목록 불러오는 중…"],
    ["Ready to export", "내보내기 준비 완료"],
    ["Review the summary, then start the export when all settings are complete.", "설정을 마친 뒤 요약 내용을 확인하고 내보내기를 시작하세요."],
    ["Connection", "연결"],
    ["Query & time range", "쿼리 및 시간 범위"],
    ["Interactive connection credentials are never stored on the Exporter server. “Remember this session” keeps them only in this browser session; scheduled exports use separate encrypted-at-rest credentials.", "대화형 연결의 인증정보는 Exporter 서버에 저장하지 않습니다. ‘이 세션에 저장’을 선택하면 현재 브라우저 세션에만 보관되며, 예약 내보내기는 별도로 암호화 저장합니다."],
    ["Export job", "내보내기 작업"],
    ["Pending", "대기 중"],
    ["Cancel", "취소"],
    ["Records", "레코드"],
    ["Transferred", "전송량"],
    ["Files", "파일"],
    ["Rate", "속도"],
    ["Source", "소스"],
    ["Partition", "분할 구간"],
    ["Queries", "쿼리 수"],
    ["Retries", "재시도"],
    ["Adaptive splits", "적응형 분할"],
    ["Duplicates skipped", "중복 제외"],
    ["Elapsed", "경과 시간"],
    ["Export record progress", "내보내기 레코드 진행률"],
    ["Waiting for total…", "전체 건수 확인 중…"],
    ["Current slice", "현재 조회 구간"],
    ["(within the full range in Export Summary)", "(내보내기 요약의 전체 시간 범위 내)"],
    ["Waiting to start", "시작 대기 중"],
    ["Run export", "내보내기 실행"],
    ["Export History", "내보내기 기록"],
    ["Recent jobs persist across exporter restarts without storing credentials or raw queries.", "인증정보나 원본 쿼리를 저장하지 않고 최근 작업 기록을 유지합니다."],
    ["Created", "생성 시각"],
    ["Status", "상태"],
    ["Sources", "데이터 소스"],
    ["Range", "시간 범위"],
    ["Records / Size", "레코드 / 크기"],
    ["Checkpoint", "체크포인트"],
    ["Action", "작업"],
    ["Result", "결과"],
    ["Loading export history…", "내보내기 기록 불러오는 중…"],
    ["Stored metadata excludes API tokens, S3 credentials, SFTP passwords/private keys, and raw query contents. Resume verifies completed split parts by SHA-256; re-enter the original settings and credentials before resuming.", "저장된 작업 정보에는 API 토큰, S3 인증정보, SFTP 비밀번호·개인키 및 원본 쿼리가 포함되지 않습니다. 재개 시 완료된 파일 조각을 SHA-256으로 검증합니다. 재개 전 원래 설정과 인증정보를 다시 입력하세요."],
    ["EXPORT SUMMARY", "내보내기 요약"],
    ["Not set", "미설정"],
    ["Not selected", "미선택"],
    ["Alerts", "경고(Alerts)"],
    ["None", "없음"],
    ["Matched", "일치 건수"],
    ["File split", "파일 분할"],
    ["Single file", "단일 파일"],
    ["Browser download", "브라우저 다운로드"],
    ["Review only · Run export is available after Destination settings.", "요약 확인용 · 전송 대상을 설정한 뒤 내보내기를 실행하세요."],
    ["LARGE EXPORT WARNING", "대용량 내보내기 경고"],
    ["This export may degrade system performance", "이 내보내기는 시스템 성능에 영향을 줄 수 있습니다"],
    ["A large number of records matched this query.", "이 쿼리에 많은 레코드가 일치합니다."],
    ["Large queries can increase load on Stellar Cyber and the Exporter. Reduce the time range, query, or selected data sources when possible.", "대량 조회는 Stellar Cyber와 Exporter의 부하를 높일 수 있습니다. 가능하면 시간 범위, 쿼리 또는 데이터 소스 범위를 줄이세요."],
    ["Go back and refine", "돌아가서 조건 수정"],
    ["Export anyway", "계속 내보내기"],
    ["download", "다운로드"],
    ["No accessible tenants returned", "접근 가능한 테넌트 없음"],
    ["Select one tenant…", "테넌트 하나 선택…"],
    ["No accessible tenants were returned for this credential.", "이 인증정보로 접근 가능한 테넌트가 없습니다."],
    ["Select at least one data source.", "데이터 소스를 하나 이상 선택하세요."],
    ["No data source selected", "선택된 데이터 소스 없음"],
    ["Choose a valid start/end range to build the index plan.", "인덱스 조회 계획을 만들려면 올바른 시작/종료 시간을 선택하세요."],
    ["Index plan unavailable", "인덱스 조회 계획을 사용할 수 없음"],
    ["Invalid", "유효하지 않음"],
    ["No records", "레코드 없음"],
    ["The query returned no data in this range.", "선택한 범위에서 조회된 데이터가 없습니다."],
    ["No fields match this search.", "검색 조건과 일치하는 필드가 없습니다."],
    ["No export jobs yet.", "내보내기 작업 기록이 없습니다."],
    ["No scheduled exports.", "등록된 예약 작업이 없습니다."],
    ["Run now", "지금 실행"],
    ["Pause", "일시 중지"],
    ["Enable", "활성화"],
    ["Paused", "일시 중지됨"],
    ["Resume", "재개"],
    ["Saving…", "저장 중…"],
    ["Remembering…", "세션 저장 중…"],
    ["Forgetting…", "세션 지우는 중…"],
    ["Running preview…", "미리보기 실행 중…"],
    ["Loading preview…", "미리보기 불러오는 중…"],
    ["Testing connection…", "연결 테스트 중…"],
    ["Testing destination…", "전송 대상 테스트 중…"],
    ["Destination is reachable.", "전송 대상에 연결할 수 있습니다."],
    ["Fetching the SSH host key…", "SSH 호스트 키 가져오는 중…"],
    ["Fetch the current server host key first.", "먼저 현재 서버의 호스트 키를 가져오세요."],
    ["SFTP host or port changed. Fetch and trust the host key again.", "SFTP 호스트 또는 포트가 변경됐습니다. 호스트 키를 다시 가져와 확인하세요."],
    ["SSH host-key verification is disabled for this destination. This is not recommended.", "이 전송 대상의 SSH 호스트 키 검증이 꺼졌습니다. 권장하지 않습니다."],
    ["Fetch and trust the SFTP server host key before testing or exporting.", "테스트하거나 내보내기 전에 SFTP 서버 호스트 키를 가져와 신뢰 대상으로 등록하세요."],
    ["Stellar Cyber Query cannot be empty.", "Stellar Cyber 쿼리를 입력하세요."],
    ["Query must be a JSON object.", "쿼리는 JSON 객체여야 합니다."],
    ["Max file size must be greater than 0.", "최대 파일 크기는 0보다 커야 합니다."],
    ["Export record limit must be a positive whole number.", "내보내기 건수 제한은 양의 정수여야 합니다."],
    ["Choose start and end time to build the effective DSL.", "최종 DSL을 만들려면 시작 및 종료 시간을 선택하세요."],
    ["Start and end time are required.", "시작 및 종료 시간을 입력하세요."],
    ["End time must be later than start time.", "종료 시각은 시작 시각보다 늦어야 합니다."],
    ["Stellar Cyber host is required.", "Stellar Cyber 호스트를 입력하세요."],
    ["Account email is required for Root Scope.", "Root Scope에서는 계정 이메일이 필요합니다."],
    ["User API Key is required.", "사용자 API Key를 입력하세요."],
    ["All-Access Token is required.", "All-Access Token을 입력하세요."],
    ["Select one tenant before querying or exporting.", "조회하거나 내보내기 전에 테넌트 하나를 선택하세요."],
    ["Enter the SFTP host first.", "먼저 SFTP 호스트를 입력하세요."],
    ["S3 bucket is required.", "S3 버킷을 입력하세요."],
    ["S3 access key is required.", "S3 액세스 키를 입력하세요."],
    ["S3 secret key is required.", "S3 비밀 키를 입력하세요."],
    ["SFTP host is required.", "SFTP 호스트를 입력하세요."],
    ["SFTP username is required.", "SFTP 사용자 이름을 입력하세요."],
    ["SFTP password is required.", "SFTP 비밀번호를 입력하세요."],
    ["SFTP private key is required.", "SFTP 개인키를 입력하세요."],
    ["Trust the current SFTP SSH host key before testing or exporting.", "테스트 또는 내보내기 전에 현재 SFTP SSH 호스트 키를 신뢰 대상으로 등록하세요."],
    ["Select at least one export field.", "내보낼 필드를 하나 이상 선택하세요."],
    ["Enter a profile name.", "프로필 이름을 입력하세요."],
    ["Profile saved locally without credentials.", "인증정보를 제외하고 브라우저에 프로필을 저장했습니다."],
    ["Select a saved profile.", "저장된 프로필을 선택하세요."],
    ["Profile loaded. Credentials remain session-only.", "프로필을 불러왔습니다. 인증정보는 브라우저 세션에서만 유지됩니다."],
    ["Profile deleted.", "프로필을 삭제했습니다."],
    ["Host and User API Key are required.", "호스트와 사용자 API Key가 필요합니다."],
    ["Host, account email, and All-Access Token are required.", "호스트, 계정 이메일, All-Access Token을 입력하세요."],
    ["Test the connection and select exactly one tenant before saving.", "저장 전에 연결 테스트를 실행하고 테넌트 하나를 선택하세요."],
    ["Remembered for this browser session only. This connection is not stored on the Exporter server and is not shared with other browsers or devices.", "현재 브라우저 세션에만 연결정보를 저장했습니다. Exporter 서버나 다른 브라우저·기기에는 저장되지 않습니다."],
    ["Session forgotten. Host, credential, tenant, and connection results were cleared from this page.", "세션 정보를 지웠습니다. 이 화면의 호스트, 인증정보, 테넌트 및 연결 결과가 초기화됐습니다."],
    ["Restoring saved session tenant…", "저장된 세션 테넌트 복원 중…"],
    ["Restoring remembered tenant…", "저장한 테넌트 복원 중…"],
    ["Automatic tenant restore failed — Test connection to retry", "테넌트 자동 복원에 실패했습니다. 연결 테스트를 다시 실행하세요."],
    ["Browser-session Host and credential were restored, but the tenant could not be verified automatically. Press Test connection to retry.", "브라우저 세션의 호스트와 인증정보는 복원했지만 테넌트를 자동 검증할 수 없습니다. 연결 테스트를 다시 실행하세요."],
    ["Browser-session connection restored. Test connection to select a tenant, then remember the session again.", "브라우저 세션 연결을 복원했습니다. 연결 테스트로 테넌트를 선택하고 세션을 다시 저장하세요."],
    ["Temporary browser-session connection data was invalid and has been cleared.", "브라우저 세션의 연결정보가 유효하지 않아 삭제했습니다."],
    ["Connection settings changed. Test connection again to reload accessible tenants.", "연결 설정이 변경됐습니다. 연결 테스트를 다시 실행해 접근 가능한 테넌트를 불러오세요."],
    ["Current connection values changed. Browser-session memory is unchanged until you press Remember this session again.", "현재 연결 값이 변경됐습니다. ‘이 세션에 저장’을 다시 누르기 전까지 저장된 세션 정보는 바뀌지 않습니다."],
    ["Credentials changed — test connection again", "인증정보가 변경됐습니다. 연결 테스트를 다시 실행하세요."],
    ["Relative time must be a positive number.", "상대 시간은 양수여야 합니다."],
    ["Valid JSON. Time range will be injected as a non-overlapping filter.", "JSON 형식이 유효합니다. 시간 범위는 중복되지 않는 필터로 추가됩니다."],
    ["Stellar Cyber Query is ready. Lucene syntax is validated by Stellar Cyber when Preview runs.", "Stellar Cyber 쿼리가 준비됐습니다. Lucene 문법은 미리보기 실행 시 Stellar Cyber에서 검증됩니다."],
    ["Preparing…", "준비 중…"],
    ["Preparing", "준비 중"],
    ["Exporting", "내보내는 중"],
    ["Cancelling", "취소 중"],
    ["Cancelling…", "취소 중…"],
    ["Export running…", "내보내는 중…"],
    ["Running export…", "내보내기 실행 중…"],
    ["Reconnecting export…", "내보내기 다시 연결 중…"],
    ["Export status unavailable", "내보내기 상태를 확인할 수 없음"],
    ["Awaiting confirmation…", "사용자 확인 대기 중…"],
    ["Resuming…", "재개 중…"],
    ["Working…", "처리 중…"],
    ["Export cancelled.", "내보내기를 취소했습니다."],
    ["Export failed.", "내보내기에 실패했습니다."],
    ["Cancellation requested. Finishing the current operation safely…", "취소 요청을 받았습니다. 현재 작업을 안전하게 마무리하는 중…"],
    ["Schedule name is required.", "예약 이름을 입력하세요."],
    ["Schedule interval must be a positive whole number.", "예약 실행 간격은 양의 정수여야 합니다."],
    ["Schedule lookback window must be a positive whole number.", "예약 조회 범위는 양의 정수여야 합니다."],
    ["Scheduled exports require an S3 or SFTP destination.", "예약 내보내기에는 S3 또는 SFTP 대상이 필요합니다."],
    ["Scheduled export started…", "예약 내보내기 시작…"],
    ["Scheduled export completed.", "예약 내보내기 완료."],
    ["Scheduled export is still running.", "예약 내보내기가 아직 실행 중입니다."],
    ["Schedule enabled.", "예약 작업을 활성화했습니다."],
    ["Schedule paused.", "예약 작업을 일시 중지했습니다."],
    ["Schedule deleted.", "예약 작업을 삭제했습니다."],
    ["Another export is already active.", "이미 다른 내보내기 작업이 진행 중입니다."],
    ["Settings locked. Validating saved checkpoint against the current export settings…", "설정을 잠갔습니다. 저장된 체크포인트와 현재 설정을 검증하는 중…"],
    ["The previously active export is no longer available. Settings were unlocked.", "이전 내보내기 작업을 더 이상 찾을 수 없어 설정 잠금을 해제했습니다."],
    ["Reconnecting to the active export. Settings are locked until the job reaches a terminal state…", "진행 중인 내보내기에 다시 연결하는 중입니다. 작업이 끝날 때까지 설정이 잠깁니다…"],
    ["Export completed while this page was reconnecting. Download started.", "화면 재연결 중 내보내기가 완료돼 다운로드를 시작했습니다."],
    ["Reconnected to the active export. Original settings remain locked to this job.", "진행 중인 작업에 다시 연결했습니다. 원래 설정은 작업 완료까지 잠깁니다."],
    ["This large export may degrade system performance.", "이 대용량 내보내기는 시스템 성능에 영향을 줄 수 있습니다."],
    ["The exporter service could not be reached. The Exporter backend or reverse proxy may be restarting or offline. Wait a moment and retry.", "Exporter 서비스에 연결할 수 없습니다. 백엔드 또는 리버스 프록시가 재시작 중이거나 중단됐을 수 있습니다. 잠시 후 다시 시도하세요."],
    ["The exporter service could not be reached after automatic retries.", "자동 재시도 후에도 Exporter 서비스에 연결할 수 없습니다."],
    ["Completed", "완료"],
    ["completed", "완료"],
    ["failed", "실패"],
    ["cancelled", "취소됨"],
    ["expired", "만료됨"],
    ["interrupted", "중단됨"],
    ["running", "실행 중"],
    ["pending", "대기 중"],
    ["waiting", "대기 중"],
    ["paused", "일시 중지"],
    ["unknown", "알 수 없음"],
    ["(empty query)", "(빈 쿼리)"],
    ["Unchanged", "변경 없음"]
  ]);

  // UI values containing counts, names or dates need parameter-aware translations.
  const templates = [
    [/^([\d,]+) sources?$/, (m) => m[1] + "개 데이터 소스"],
    [/^([\d,]+) selected$/, (m) => m[1] + "개 선택됨"],
    [/^([\d,]+) fields? selected$/, (m) => m[1] + "개 필드 선택됨"],
    [/^([\d,]+) saved parts?$/, (m) => m[1] + "개 파일 조각 저장됨"],
    [/^Every ([\d,]+) min$/, (m) => m[1] + "분마다"],
    [/^([\d,]+) min first run$/, (m) => "첫 실행 " + m[1] + "분"],
    [/^Selected tenant: (.+)\. Preview, count, export and schedules are restricted to this tenant\.$/, (m) => "선택한 테넌트: " + m[1] + ". 조회·건수 확인·내보내기·예약 작업은 이 테넌트로 제한됩니다."],
    [/^Saved tenant restored: (.+)\.$/, (m) => "저장된 테넌트 복원: " + m[1]],
    [/^1 tenant found and selected: (.+)\.$/, (m) => "테넌트 1개 발견 및 선택: " + m[1]],
    [/^([\d,]+) tenants available\. Select exactly one tenant before querying or exporting\.$/, (m) => "테넌트 " + m[1] + "개를 사용할 수 있습니다. 조회나 내보내기 전에 하나를 선택하세요."],
    [/^Index planner error: (.+)$/, (m) => "인덱스 조회 계획 오류: " + m[1]],
    [/^Preview loaded: ([\d,]+) rows shown\.$/, (m) => "미리보기 완료: " + m[1] + "개 행 표시."],
    [/^Preview loaded: ([\d,]+) rows shown\. Warning: (.+)$/, (m) => "미리보기 완료: " + m[1] + "개 행 표시. 경고: " + m[2]],
    [/^(.+) copied$/, (m) => m[1] + " 복사 완료"],
    [/^Checking count… (.+)$/, (m) => "건수 확인 중… " + m[1]],
    [/^Settings locked\. Counting the selected tenant\/source\/day ranges… (.+) elapsed\. Large ranges can take several minutes\.$/, (m) => "설정 잠금 중. 테넌트·소스·날짜별 데이터 건수 확인 중… 경과 " + m[1] + ". 대용량 조회는 수분이 걸릴 수 있습니다."],
    [/^Count check complete: ([\d,]+) records\. Creating locked export job…$/, (m) => "건수 확인 완료: " + m[1] + "건. 설정을 잠그고 내보내기 작업을 생성합니다…"],
    [/^Schedule saved securely\. Next run: (.+)\.$/, (m) => "예약 정보를 암호화 저장했습니다. 다음 실행: " + m[1]],
    [/^Scheduled export finished with status: (.+)\.$/, (m) => "예약 내보내기 종료. 상태: " + m[1]],
    [/^Restoring session tenant: (.+)…$/, (m) => "세션 테넌트 복원 중: " + m[1] + "…"],
    [/^Restoring remembered tenant (.+)…$/, (m) => "저장한 테넌트 " + m[1] + " 복원 중…"],
    [/^Session connection restored\. Tenant (.+) is ready\.$/, (m) => "세션 연결 복원 완료. 테넌트 " + m[1] + " 준비됨."],
    [/^Browser-session connection and tenant (.+) restored automatically\.$/, (m) => "브라우저 세션 연결과 테넌트 " + m[1] + "를 자동 복원했습니다."],
    [/^Browser-session connection restored\. Restoring tenant (.+) automatically…$/, (m) => "브라우저 세션 연결 복원 완료. 테넌트 " + m[1] + " 자동 복원 중…"],
    [/^Could not restore (.+) — Test connection to retry$/, (m) => m[1] + " 복원 실패. 연결 테스트를 다시 실행하세요."],
    [/^Resuming export after ([\d,]+) verified completed part\(s\)… Settings remain locked to this job\.$/, (m) => "검증된 파일 조각 " + m[1] + "개부터 내보내기를 재개합니다… 이 작업이 끝날 때까지 설정은 잠깁니다."],
    [/^Completed: (.+) · ([\d,]+) records · (.+) transferred\.$/, (m) => "완료: " + m[1] + " · " + m[2] + "건 · 전송량 " + m[3] + "."],
    [/^Completed: ([\d,]+) records · (.+) ready\. Download started\.$/, (m) => "완료: " + m[1] + "건 · " + m[2] + " 다운로드 준비 완료. 다운로드를 시작했습니다."],
    [/^(.+) The export may still be running\. Settings remain locked; reload this page to reconnect safely\.$/, (m) => m[1] + " 내보내기가 아직 실행 중일 수 있습니다. 설정은 잠긴 상태입니다. 새로고침하여 안전하게 다시 연결하세요."],
    [/^([\d,]+) records$/, (m) => m[1] + "건"],
    [/^([\d,]+) \/ ([\d,]+) records · (.+)$/, (m) => m[1] + " / " + m[2] + "건 · " + m[3]],
    [/^([\d,.]+) rec\/s$/, (m) => m[1] + "건/초"],
    [/^([a-zA-Z]+)… (.+) · (.+) transferred(.*)\. Settings remain locked to this job\.$/, (m) => ({Preparing:"준비 중",Exporting:"내보내는 중",Cancelling:"취소 중"}[m[1]] || m[1]) + "… " + m[2] + " · 전송량 " + m[3] + m[4] + ". 이 작업이 끝날 때까지 설정이 잠깁니다."],
    [/^(\d+) adaptive splits?$/, (m) => "적응형 분할 " + m[1] + "회"],
    [/^([\d,]+) selected fields?$/, (m) => m[1] + "개 필드 선택됨"]
  ];

  const textSources = new WeakMap();
  const attributeSources = new WeakMap();
  let language = "en";

  function translate(message) {
    const input = String(message == null ? "" : message);
    if (language !== "ko") return input;
    const trimmed = input.trim();
    if (!trimmed) return input;
    let localized = korean.get(trimmed);
    if (localized === undefined) {
      for (const [regex, format] of templates) {
        const match = regex.exec(trimmed);
        if (match) {
          localized = format(match);
          break;
        }
      }
    }
    if (localized === undefined && trimmed.includes(", ")) {
      // Source descriptions can be rendered as a comma-separated summary.
      const parts = trimmed.split(", ");
      if (parts.every((part) => korean.has(part))) {
        localized = parts.map((part) => korean.get(part)).join(", ");
      }
    }
    if (localized === undefined) return input;
    return input.slice(0, input.indexOf(trimmed)) + localized +
      input.slice(input.indexOf(trimmed) + trimmed.length);
  }

  function excluded(node) {
    const element = node.nodeType === 3 ? node.parentElement : node;
    return !element || Boolean(element.closest(
      "script,style,textarea,pre,code,#previewTable td,#previewTable th,[contenteditable],[data-no-translate]"
    ));
  }

  function syncText(node) {
    if (!node || node.nodeType !== 3 || excluded(node)) return;
    const current = node.nodeValue;
    const old = textSources.get(node);
    const source = !old || (current !== old.rendered && current !== old.source)
      ? current : old.source;
    const rendered = translate(source);
    textSources.set(node, {source, rendered});
    if (current !== rendered) node.nodeValue = rendered;
  }

  function syncAttributes(element) {
    if (!element || element.nodeType !== 1 || excluded(element)) return;
    const cached = attributeSources.get(element) || {};
    for (const attribute of ["placeholder", "title", "aria-label"]) {
      if (!element.hasAttribute(attribute)) continue;
      const current = element.getAttribute(attribute);
      const old = cached[attribute];
      const source = !old || (current !== old.rendered && current !== old.source)
        ? current : old.source;
      const rendered = translate(source);
      cached[attribute] = {source, rendered};
      if (current !== rendered) element.setAttribute(attribute, rendered);
    }
    attributeSources.set(element, cached);
  }

  function translateTree(root) {
    if (!root) return;
    if (root.nodeType === 3) { syncText(root); return; }
    if (root.nodeType !== 1 || excluded(root)) return;
    syncAttributes(root);
    const elements = root.querySelectorAll("*");
    for (const element of elements) syncAttributes(element);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) syncText(walker.currentNode);
  }

  function sourceText(element) {
    const first = element && element.firstChild;
    if (!first || first.nodeType !== 3) return element?.textContent || "";
    return textSources.get(first)?.source || first.nodeValue;
  }

  function setLanguage(locale) {
    language = locale === "ko" ? "ko" : "en";
    document.documentElement.lang = language;
    document.title = language === "ko" ? "Stellar Cyber 데이터 내보내기" : "Stellar Cyber Data Exporter";
    const select = document.getElementById("uiLanguage");
    if (select) select.value = language;
    try { localStorage.setItem(STORAGE_KEY, language); } catch { /* blocked storage */ }
    translateTree(document.body);
    document.dispatchEvent(new CustomEvent("exporter:languagechange", {detail: {language}}));
  }

  function initialize() {
    try { language = localStorage.getItem(STORAGE_KEY) === "ko" ? "ko" : "en"; }
    catch { language = "en"; }
    const select = document.getElementById("uiLanguage");
    if (select) {
      select.value = language;
      select.addEventListener("change", () => setLanguage(select.value));
    }
    document.documentElement.lang = language;
    document.title = language === "ko" ? "Stellar Cyber 데이터 내보내기" : "Stellar Cyber Data Exporter";
    translateTree(document.body);
    const observer = new MutationObserver((changes) => {
      for (const change of changes) {
        if (change.type === "characterData") syncText(change.target);
        else if (change.type === "attributes") syncAttributes(change.target);
        else for (const node of change.addedNodes) translateTree(node);
      }
    });
    observer.observe(document.body, {
      childList: true, characterData: true, subtree: true,
      attributes: true, attributeFilter: ["placeholder", "title", "aria-label"]
    });
  }

  window.ExporterI18n = Object.freeze({
    get language() { return language; },
    t: translate,
    sourceText,
    setLanguage
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
