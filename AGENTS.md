<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## E2E Test Resource Policy

1. E2E 테스트는 명시적으로 필요한 경우에만 실행한다.
2. 코드 수정마다 전체 E2E 테스트를 실행하지 않는다.
3. 우선 Lint, TypeCheck, Unit Test를 수행한다.
4. E2E는 변경된 기능의 테스트만 실행한다.
5. Playwright workers는 최대 1개로 제한한다.
6. 같은 프로젝트에서 E2E 중복 실행을 금지한다.
7. 테스트 실패 시 무한 재시도하지 않는다.
8. 동일 실패에 대한 자동 재실행은 최대 1회로 제한한다.
9. E2E 실행 전 기존 테스트 프로세스를 확인한다.
10. 테스트가 종료되면 브라우저가 정상 종료되었는지 확인한다.
11. 전체 E2E 테스트는 작업 완료 단계에서만 실행한다.
12. 문제 분석에 필요한 경우에만 Trace/Video를 활성화한다.
13. 테스트 실패 시 원인과 실행 로그를 보고한다.
