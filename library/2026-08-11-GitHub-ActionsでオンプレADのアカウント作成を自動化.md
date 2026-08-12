---
url: https://techblog.zozo.com/entry/new-employee-account-automation
created: '2026-08-11T20:15:40'
type: article
tags:
- githubactions
- powershell
- kintone
- activeDirectory
summary: 'kintoneから入社データを取得し、GitHub Actionsとself-hosted runnerを用いて閉域オンプレADのアカウント作成を自動化する取り組みを解説。

  散在していた業務ロジックをPowerShellスクリプトとしてコード化し、リポジトリで一元管理することで、手作業による課題を解決。

  Microsoft Entra ConnectやGraph APIのオンデマンドプロビジョニングを活用し、クラウド側への即時反映を実現。'
---

# 閉域のオンプレADをGitHub Actionsで操作する ── self-hosted runnerによるアカウント作成の自動化
2026-08-11
![閉域のオンプレADをGitHub Actionsで操作する ── self-hosted runnerによるアカウント作成の自動化](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260715/20260715112341.png)

## はじめに

こんにちは、コーポレートエンジニアリング部ITサービスブロックの高塩です。2026年2月に入社し、社内の共通システムやIdP、SaaSの管理、日々のオペレーション自動化などを担当しています。

ZOZOでは入社者のマスタデータをkintoneで管理しています。入社のたびに、Active Directory（以下、AD）を起点にMicrosoft 365・Google Workspace・Boxなどでアカウントを作成し、利用できる状態まで整えています。この作業は長らく手作業で運用してきましたが、工数や属人化、そしてCSVの受け渡しに課題を抱えていました。

オンプレADやLDAPサーバーを長く運用してきた組織では、それが自動化の足枷になっているケースも少なくないと思います。かといって、すべてをクラウドへすぐに寄せられるとも限りません。本記事では、この一連のアカウント作成を、kintoneを起点にGitHub Actions（self-hosted runner）で自動化した取り組みを紹介します。閉域にあるオンプレADの操作までGitHub Actionsに載せ、コードレビュー・実行ログ・再現性といったCI/CDの利点をアカウント運用に持ち込みました。

## 目次

## 背景：手作業時代のフローと課題

自動化前のアカウント作成は、おおよそ次のような流れでした。

1. GASでkintoneから入社者のレコードを取得する
2. スプレッドシートに転記し、関数で表示名やグループなどの値を加工する
3. 加工した結果をCSVでエクスポートし、オンプレミスの作業サーバーへ手動で転送する
4. 作業サーバー上で複数のPowerShellスクリプトにCSVを読み込ませ、順次実行してアカウントを作成する
5. 途中、Microsoft Entra Connectのデルタ同期を手動で実行し、各SaaSへの反映を待つ
6. 反映後、各SaaSの個別設定を、設定用スクリプトの実行や手作業で投入する

![手作業時代のアカウント作成フロー](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260701/20260701120932.png)

一見すると回っているように見えますが、運用を続けるうちに次のような課題が積み重なっていました。

- **業務ロジックが散在している** ：誰が・どの雇用形態で・どのグループに入るのか、その判断ロジックがスプレッドシートの関数と作業サーバー上のスクリプトに分散していました。そのため全体像の把握が困難でした。
- **手作業でのCSV転送** ：スプレッドシートからCSVをエクスポートし、作業サーバーへ人手で転送していました。
- **ログの視認性が低い** ：実行は作業サーバーのコンソールで行うため、いつ・誰が・何を流したのかが後から追いにくい状態でした。
- **スクリプトのドリフト** ：Gitリポジトリ上のスクリプトと、作業サーバーに置かれた実際に動くスクリプトが少しずつ乖離していき、「リポジトリのコード＝実際に動いているコード」と言い切れなくなっていました。

これらをまとめて解決するために、フロー全体を作り直すことにしました。

## 全体アーキテクチャ

新しい仕組みでは、データはkintoneから直接取り、全工程をGitHub Actionsから動かすことにしました。

![自動化後のアーキテクチャ](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260701/20260701144517.png)

手作業のころから大きく変えたのは、次の3つです。

- **CSVの受け渡しをやめ、kintone APIを直接呼び出す** ：人の手によるエクスポートと加工を排除しました。
- **散在していた業務ロジックをコードに集約する** ：判断ロジックをすべてPowerShellスクリプトにまとめ、Gitリポジトリで管理するようにしました。
- **オンプレADの操作にself-hosted runnerを使う** ：GitHub Actionsの仕組みに乗りながら、オンプレミスのADコマンドレットをそのまま実行できるようにしました。

ワークフローは `schedule` によるcron実行で動きます。kintoneからはデフォルトで翌月の入社者を取得するので、毎月決まった日に翌月分の作成予定をSlackへ自動投稿し、その翌日にまとめて作成する、という運用にしました。

ここからは、土台となるself-hosted runner、kintoneからのアカウント作成、クラウドへの即時反映を、順に見ていきます。

## オンプレADをGitHub Actionsから操作する

この仕組みで一番頭を悩ませたのが、オンプレミスのADをどう自動化に組み込むかでした。

ADはオンプレミスの閉じたネットワークの中にあります。操作するには、次の3つが必要です。

- ドメインコントローラへ通信できるネットワーク（オンプレ内）にいること
- リモート サーバー管理ツール（ [RSAT](https://learn.microsoft.com/ja-jp/windows-server/administration/install-remote-server-administration-tools) ）の `ActiveDirectory` モジュールが入った実行環境
- 対象OUでユーザー作成とグループ追加ができるドメイン権限

最初に検討したのは、この処理を自前でオーケストレーションせず、Entra ID Governanceのようなマネージド機能に寄せる形でした。たとえばオンプレADへのユーザー作成は、 [API 駆動型インバウンド プロビジョニング](https://learn.microsoft.com/ja-jp/entra/identity/app-provisioning/inbound-provisioning-api-concepts) に任せられます。

ただ、今回の要件には合いませんでした。アカウント作成にはオンプレADのグループ操作が含まれますが、属性ベースの動的グループが扱うのはクラウドのグループで、オンプレADのグループメンバーシップまでは管理しません。ここはマネージド機能だけでは実現できません。

さらに、出し分けの業務ロジックは、手作業時代のPowerShellスクリプトへある程度作り込まれていました。これを一から組み直すより、既存の資産をそのまま流用したい事情もありました。そこで今回は、自前でオーケストレーションする方針にしました。

自前で組むなら、ADを操作する方法はいくつかあります。検討した選択肢の長所と短所を、次の表にまとめました。

| 実行方式 | 長所 | 短所・見送り理由 |
| --- | --- | --- |
| タスクスケジューラ＋スクリプト | 追加インフラが不要 | 時刻起動のみ・コードがサーバーに残りドリフト再発・ログやSecrets、レビューが弱い |
| 自前でAPIを建てる | オンデマンド実行・自由度が高い | 着信ポートの開放が必要・認証や可用性、監視を自前運用 |
| Azure Automation（Hybrid Runbook Worker） | Power Automate/Microsoft Formsから起動しやすい・Azure/M365中心の組織に馴染む | GitのPR/CIと一体化しにくい・別基盤の学習/運用コスト |
| self-hosted runner（採用） | 既存のGitHub・PR・CIにそのまま乗る・チェックアウトでドリフトなし・手動/定期の両対応 | runnerの保守が必要・信頼できるコードのみ実行する配慮が要る |

自前API以外の3方式は、オンプレからのアウトバウンド通信だけで動作し、外部に着信ポートを開ける必要がありません。

最終的に **self-hosted runner** を選びました。ADドメインに参加したWindows Server上でrunnerを動かし、PowerShellを実行しています。

コード・トリガー・ログがすべてGitHub側へ移り、サーバー上では実行時にチェックアウトされた最新のスクリプトが動くだけです。背景で挙げたドリフトは、これで自然に消えます。

ほぼ同じ仕組みは、AzureのHybrid Runbook Workerでも実現できます。私たちはGitHubを使った業務フローが根付いていたため、self-hosted runnerを選びました。

ただし、この構成では強い権限を持つrunner自体が攻撃対象になります。runnerを侵害させないことと、万一侵害されても被害を広げないことの両方に注意を払う必要があります。

runnerに任意のコードを実行させる入口はGitHubなので、次のような基本的な制御を入れています。

- リポジトリをprivateにし、権限は必要なメンバーだけに限定する
- ログインはSSOを必須とし、MFAの登録を義務づける
- mainはbranch protection ruleでCODEOWNERのレビュー承認を必須にする
- 認証は原則OIDC（Workload Identity連携）を使い、やむを得ずシークレットを使う場合もEnvironmentシークレットに置いてmainのワークフローからのみ参照できるようにする

self-hosted runnerのサービスを動かすアカウントに過剰な権限を与えないことも重要です。runnerはオンプレADからクラウドまで触れる強い実行主体なので、万一侵害されたときの影響範囲を抑えるため、アクセスできるOUを絞るなど、必要最低限の権限だけを与えています。

## kintoneから翌月の入社予定者を取得し、業務ロジックで判定してADに作成する

土台ができたら、次はアカウントを作る処理です。

まず取得です。kintoneの [Cursor API](https://cybozu.dev/ja/kintone/docs/rest-api/records/get-cursor/) を使い、クエリで対象者を絞り込みます。条件は3つで、入社月・入社区分（中途や新卒など）・雇用形態（社員やアルバイトなど）です。対象月は、定期実行では `NEXT_MONTH()` で翌月分を自動的に対象にします。

```ps1
# 入社区分・雇用形態・入社月で対象者を絞り込む
$categoryFilter = 'Category in ("中途", "新卒", "社員登用", ...)'
$contractFilter = 'Contract in ("社員", "出向", "CSアルバイト", ...)'
$query = "$categoryFilter and $contractFilter and Date = NEXT_MONTH() order by Date desc"

# カーソルを作成し、レコードを取得し切るまで繰り返す
$cursorId = (Invoke-RestMethod -Uri $cursorEndpoint -Method Post -Headers $headers -Body $utf8Body).id
$nextCursorId = $cursorId
while ($nextCursorId) {
    $res = Invoke-RestMethod -Uri "$cursorEndpoint\`?id=$nextCursorId" -Method Get -Headers $getHeaders
    $allRecords += $res.records
    $nextCursorId = $res.next
}
```

CSVのエクスポートと手動転送がなくなり、「どんな条件で対象者を抽出しているか」がクエリを見れば分かるようになりました。

ただ、取得したデータをそのままADに流し込めるわけではありません。雇用形態や所属によって、どのOUに作り、どのグループに入れるかが変わります。以前はこの出し分けがスプレッドシートの関数に埋もれていましたが、今回コード側の分岐に移しました。判定しているのは、たとえば次のような内容です。

- 雇用形態に応じた、アカウントの配置先OUの決定
- 所属に応じた、各種グループへの追加
- その他のユーザーアカウント属性の設定

判定が終わったら、self-hosted runnerの上で `ActiveDirectory` モジュールのコマンドレットを実行し、ADにアカウントを作成します。あとは次に述べる同期で、クラウド側へ反映されていきます。

## 同期待ちを能動的に潰して即時反映する

ADにユーザーを作っただけでは、クラウド側のアカウントはすぐには使えません。間に2つの同期が挟まるためです。

1つ目はAD → Entra IDです。オンプレADのユーザーは、Microsoft Entra Connectが同期して初めてEntra ID側に現れます。この同期は通常、30分間隔のサイクルでしか走りません。

2つ目はEntra ID → 各SaaSです。Entra IDからGoogle WorkspaceやBoxへは、エンタープライズアプリのプロビジョニングで連携されます。この自動プロビジョニングのサイクルは最大40分待つことがあります。

手作業のころは、この待ちを人がこなしていました。同期サイクルが回るのを待つか、待ちきれなければデルタ同期を手動で叩き、クラウドにアカウントが現れたのを確認してから次の設定に進む、という具合です。

ところが、これをそのまま自動化に持ち込むと厄介でした。AD作成の先には、Entra IDのライセンスやグループ設定、Google WorkspaceやBoxへのプロビジョニング、その後の各SaaS個別の設定が続きます。どれも前の結果を前提にした処理です。定期サイクル任せだと全部終わるまでに1時間近くかかるうえ、まだ存在しないアカウントを触って空振りするステップも出てきます。

そこで、2つの同期をワークフローから自分でトリガーし、完了を見届けてから次へ進むようにしました。

1つ目の同期は、Microsoft Entra Connectの同期サーバーに対してデルタ同期を要求し、完了するまで待ちます。runnerから `Invoke-Command` で同期サーバーに入り、 `Start-ADSyncSyncCycle` でデルタ同期を開始したあと、同期が進行中でなくなるまでポーリングします。

```ps1
Invoke-Command -ComputerName $syncServer -ScriptBlock {
    Import-Module ADSync
    Start-ADSyncSyncCycle -PolicyType Delta | Out-Null
    # 同期が完了するまで待つ
    do {
        Start-Sleep -Seconds 10
        $inProgress = (Get-ADSyncScheduler).SyncCycleInProgress
    } while ($inProgress)
}
```

ポーリングで完了を待つので、後続の処理に進む時点では、新入社員が必ずEntra ID側に存在します。

この `Invoke-Command` によるPowerShell Remotingは、runnerが侵害されたときに同期サーバーへの横移動の足がかりになりかねません。そこで、同期サーバーへ接続できる元をrunnerに限定し、接続に使うアカウントの権限も同期の実行に必要な分だけに絞っています。

### Entra ID → SaaS：Graph APIのオンデマンドプロビジョニング

2つ目の同期は、Entra IDの自動プロビジョニングのサイクルを待たず、Graph APIの [`provisionOnDemand`](https://learn.microsoft.com/ja-jp/graph/api/synchronization-synchronizationjob-provisionondemand?view=graph-rest-1.0) を使ってユーザー単位で即座にプロビジョニングをトリガーします。

このリクエストには、対象アプリのサービスプリンシパルID（ `$spId` ）・同期ジョブID（ `$jobId` ）・同期ルールID（ `$ruleId` ）の3つが必要です。ただ、こちらで用意するのは1つ目だけです。 `$spId` はエンタープライズアプリの「オブジェクトID」で、Entra管理センターのアプリのプロパティ画面に表示されます。

残りの `$jobId` と `$ruleId` は、実行時に `$spId` からGraphで取得します。ユーザーの同期ルールはアプリごとに1つしかないので、同期ジョブのスキーマを覗けば、それがそのまま使うルールです。IDを手で管理する必要はありません。

```ps1
# $spId から同期ジョブを取得（Quarantine以外を優先）
$jobs = Invoke-MgGraphRequest -Method GET \`
    -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/synchronization/jobs"
$jobId = ($jobs.value | Where-Object { $_.status.code -ne "Quarantine" } | Select-Object -First 1).id

# ジョブのスキーマから、ユーザーが対象の同期ルールを選ぶ
$schema = Invoke-MgGraphRequest -Method GET \`
    -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/synchronization/jobs/$jobId/schema"
$ruleId = ($schema.synchronizationRules |
    Where-Object { $_.objectMappings.sourceObjectName -contains "User" } |
    Select-Object -First 1).id
```

あとは、取得した `$jobId` と `$ruleId` 、そしてプロビジョニング対象のユーザーを指定してリクエストを投げます。

```ps1
$body = @{
    parameters = @(
        @{
            ruleId   = $ruleId
            subjects = @(@{ objectId = $userObjectId; objectTypeName = "User" })
        }
    )
}

Invoke-MgGraphRequest -Method POST \`
    -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/synchronization/jobs/$jobId/provisionOnDemand" \`
    -Body ($body | ConvertTo-Json -Depth 10) \`
    -ContentType "application/json"
```

この2つで同期待ちを潰すと、AD作成・各SaaSへのプロビジョニング・その後のSaaSごとの設定までが一本につながります。プロビジョニングのサイクルを待たずに済むので、後続の設定も同じ実行の中で流し込めます。終わった時点で、結果がSlackとジョブログに残ります。

## 運用：前日にdry-runで予定を流し、翌日に本番で作成する

毎月の作成は、dry-runと本番の2段階で回しています。

前日に走るのはdry-runです。AD作成やプロビジョニングといった変更は実際には行わず、「何をするか」（翌月入社者の作成予定）をSlackに流します。チームはこの通知で対象者を確認できるので、kintoneのデータに不備があっても、本番の前に気づけます。

翌日に本番が走ります。処理の開始から各ステップ、完了までを1本のSlackスレッドに流し、完了サマリーと、失敗したときのエラーだけはチャンネルにもブロードキャストして気づけるようにしています。作業サーバーのコンソールを覗かなくても、SlackとGitHub Actionsのログだけで実行状況を追えます。手作業時代に困っていた「ログの視認性の低さ」は、これで解消しました。

もう1つ効いているのが冪等性です。アカウント作成は既存ユーザーをスキップし、グループ追加も「すでにメンバー」を無視します。途中のステップが失敗しても、直して同じワークフローを流し直せば、できているところはそのまま、足りないところだけが埋まります。

また、プロビジョニングの後に各SaaSで行う個別の設定は、SaaS側の状態によっては失敗することがあります。これらは失敗しても全体を止めず、結果をSlackに残して先へ進む設定にしています。気づいたら、その部分だけ後で流し直せば済みます。

## 導入の効果

一番大きいのは、毎月の新入社員アカウント作成がほぼ無人で回るようになったことです。これまで人がCSVを受け渡し、スクリプトを手で実行し、同期を待っていた一連の作業が、1回のワークフロー実行にまとまりました。

業務ロジックもコードに集まり、「どの条件で何が付与されるか」をリポジトリで追えます。リポジトリのコードと実際に動くコードが一致するので、ドリフトも起きません。

## まとめ

本記事では、新入社員のアカウント作成を、kintoneを起点にGitHub Actionsで自動化した取り組みを紹介しました。オンプレADの操作はself-hosted runnerで担い、散らばっていた業務ロジックはコードにまとめ、同期待ちはGraph APIのオンデマンドプロビジョニングで潰しました。手作業で属人化していた運用を、コード化して実行を追える形にできました。

オンプレミスとクラウドが混在する環境でアカウント運用を自動化したい方の参考になれば幸いです。今後は、退職時のアカウント無効化など、入社から退職までのライフサイクル全体へ自動化を広げていく予定です。

ZOZOでは、一緒にサービスを作り上げてくれる方を募集中です。ご興味のある方は、以下のリンクからぜひご応募ください。

<iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fcorp.zozo.com%2Frecruit%2F" title="採用 - 株式会社ZOZO" frameborder="0"></iframe>[corp.zozo.com](https://corp.zozo.com/recruit/)
