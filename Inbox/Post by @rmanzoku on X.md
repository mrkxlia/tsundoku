https://x.com/rmanzoku/status/2031648194531061984?s=12&t=22GY_jUSQsg0NcuE2S9fmA
# Post by @rmanzoku on X
2026-08-11
だいぶリポジトリやプロジェクトによらないグローバルのCLAUDE.md (~/.claude/CLAUDE.md)に書くべきことがまとまってきた。

今はこんな感じ

・MCP禁止: MCPを使わずCLIを使え  
・Memory管理: Worktreeベースでやってるのでセッションを跨いだMemoryは使えない、git管理しろ  
・一時ファイル: Subagentや別Agentが読むので.context以下に一時ファイルを作れ。掃除が面倒なので/tmp/とかに作るな  
・ADR: 大きめの変更は常にADR（Architecture Decision Records）を作って保存しろ  
・Plan Review: Planを人間に出す前にAIレビューしてIssueを潰してからだせ  
・Auto memory: Auto memoryの内容は適切にドキュメント化しろ

皆さんはどういうの書いてますか？