---
url: https://techblog.zozo.com/entry/just-in-time-access-company-wide-rollout-at-zozo
created: '2026-08-11T20:15:40'
type: article
tags:
- aws
- jitアクセス
- セキュリティ
- zozo
- iam
summary: 'ZOZOはAWSでの最小権限原則を徹底するため、JITアクセスの全社導入を実施した。

  OSSのTEAMを活用し、申請の幅を確保しつつ承認権限を各アカウント管理者へ委譲した。

  導入後に発生した運用課題には、個別Permission Setの柔軟な設定制御で対応している。'
title: AWSの強い権限は使い捨てに ── ZOZOがJITアクセスを全社導入した設計と運用
read: false
shelf_life: medium
published_at: '2026-07-10'
---

# AWSの強い権限は使い捨てに ── ZOZOがJITアクセスを全社導入した設計と運用
2026-08-11
![AWSの強い権限は使い捨てに ── ZOZOがJITアクセスを全社導入した設計と運用](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260709/20260709114452.png)

## はじめに

こんにちは、全社AWS管理部門の江島です。社内で利用されているAWS環境を全社横断的に管理する役割を担っています。

全社AWS管理部門では、AWSを安全に運用するために日頃からさまざまな取り組みを行っています。例えば、AWS本番環境へのアクセス管理においてIAM Identity Centerを活用し、定期的な棚卸しや申請ベースの権限管理といったセキュリティ対策を継続的に実施してきました。

こうした取り組みを土台としつつ、さらなるセキュリティ強化に向けて「必要なときだけ権限を付与する」最小権限の原則を徹底することを次の目標に掲げました。

本記事では、JITアクセス（ジャストインタイムアクセス）の仕組みを全社に導入した取り組みをご紹介します。AWSがオープンソースで公開する「TEAM（Temporary Elevated Access Management）」を活用しました。

## 目次

## 従来の運用 / 課題

従来の権限付与フローは以下の通りです。

![従来の権限付与フロー](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260625/20260625211737.png)

まず、申請者が社内ツールにて権限を申請します。その後、セキュリティ部門が内容の妥当性を確認し、全社AWS管理部門が権限を付与します。

なお、定期的な棚卸しや利用者からの申請に応じた見直しは実施していたものの、権限自体は常時付与された状態でした。

付与する権限が申請理由と照らし合わせて妥当であることは都度確認されていますが、必要時にだけ利用できれば良いような **強い権限** を常に保持しておくことは、最小権限の原則に照らしてリスクになり得ます。

そこで、これを解決するために「JITアクセス」の仕組みを導入することになりました。

## JITアクセスとは

JITアクセス（ジャストインタイムアクセス）とは一時的に権限昇格するための仕組みです。IAM Identity Centerの公式ドキュメントでは次のように説明されています。

> Temporary elevated access (also known as just-in-time access) is a way to request, approve, and track the use of a permission to perform a specific task during a specified time.

引用元： <iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fdocs.aws.amazon.com%2Fsinglesignon%2Flatest%2Fuserguide%2Ftemporary-elevated-access.html" title="Temporary elevated access for AWS accounts - AWS IAM Identity Center" frameborder="0"></iframe>[docs.aws.amazon.com](https://docs.aws.amazon.com/singlesignon/latest/userguide/temporary-elevated-access.html)

これを活用することで、本記事のタイトルにある「強い権限は使い捨て」を実現できます。

なお、前述したIAM Identity Centerの公式ドキュメントに記載があるように、さまざまなSaaSがIAM Identity Centerと連携してJITアクセスの機能を提供しています。また、AWSとしても独自のOSS（後述するTEAMというアプリケーション）を提供しています。

比較検討を行った結果、コストが安価であり、国内外のさまざまな企業での導入実績もあるTEAMを採用することになりました。

## TEAM （Temporary Elevated Access Management）

TEAMとはAWSによって提供されている一時的に権限昇格するためのアプリケーションです。以下のリポジトリで公開されています。

<iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fgithub.com%2Faws-samples%2Fiam-identity-center-team" title="GitHub - aws-samples/iam-identity-center-team: Open-source temporary elevated access solution for AWS IAM Identity Center." frameborder="0"></iframe>[github.com](https://github.com/aws-samples/iam-identity-center-team)

AWS LambdaやAmazon DynamoDBのように複数のサーバレスサービスで構成されており、安価で拡張性を持ったアーキテクチャです。

公式ドキュメントからの引用ですが、具体的なアーキテクチャは以下の通りです。詳細は引用元をご参照ください。

![](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260708/20260708201852.png)

TEAMのアーキテクチャ https://aws-samples.github.io/iam-identity-center-team/docs/overview/architecture.html より引用

TEAMを組織へ導入するには運用面でさまざまな点を検討する必要があります。具体的には、以下のような観点があります。

- JITアクセスの対象とする権限
- 新しい権限付与フロー
- IdP管理
- 承認可能な範囲の決定（Approver Policy）
- 申請可能な範囲の決定（Eligibility Policy）

以降、それぞれの検討ポイントについて具体的な内容を紹介します。

## TEAMの導入に必要な検討ポイント

### JITアクセスの対象とする権限

IAM Identity Centerを利用しているため、各ユーザへ付与する権限はPermission Setで管理しています。当社ではユーザの役割に応じて複数のPermission Setを用意しており、「読み取り専用」や「書き込みも可能」な権限があります。

結論としては、常に保有可能な権限は「読み取り専用」のみ、「書き込みも可能」な権限については **すべてJITアクセスの対象** としました。これについては運用とセキュリティのトレードオフを考える必要がありますが、システムを安全に運用することを最優先とするために厳しめの方針となっています。なお、読み取り専用といっても、機密性が高い情報についてはさらに細かなアクセス制御を別途行っています。

### 新しい権限付与フロー

JITアクセスによる権限付与フローは以下の通りです。

![新しい権限付与フロー](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260625/20260625211751.png)

このフローを実現するために、一連のやり取りで登場する役割を整理しました。

| 役割 | 従来の権限付与フロー | 新しい権限付与フロー（JITアクセス） |
| --- | --- | --- |
| 申請者 | 権限の申請 | 権限の申請 |
| セキュリティ部門 | 申請内容を都度確認 | **AWSアカウント管理者へ判断を委譲** |
| 全社AWS管理部門 | 申請ごとに権限付与 | **AWSアカウント管理者へ作業権限を委譲** |
| AWSアカウント管理者 | \- | **JITアクセス承認者の管理・承認** |
| JITアクセス承認者 | \- | **JITアクセスの承認操作** |

新しいフローを実現するために、「AWSアカウント管理者」および「JITアクセス承認者」の役割を新しく定義しました。なお、セキュリティ部門はAWSアカウント管理者の任命に関する判断は引き続き実施します。また、AWSアカウント管理者は自身もJITアクセス承認者の役割を担います。

当社は多くのAWSアカウントを保有しているため、従来のフローのままですべての承認作業を行うことが困難でした。そこで、最低限のガバナンスを維持した上で権限を委譲する方針としています。

元々、AWSアカウントを新規で発行する際にはAWSアカウントごとに管理者を立ててもらう運用としていました。そこで、AWSアカウント管理者にJITアクセスの承認権限も委譲することにしました。一方で、単純に権限を委譲するだけだとAWSアカウント管理者自身の負担が増大すると想定されたので、JITアクセスの承認者についてはAWSアカウント管理者自身でコントロール可能なルールとしました。

### IdP管理

TEAMはIdP（Identity Provider）であるIAM Identity Centerのグループ機能を前提として動きます。具体的には、以下のような役割をグループとして用意する必要があります。

| 役割 | 説明 |
| --- | --- |
| TEAM管理者 | TEAM自体の設定を変更する権限を持つ |
| TEAM監査者 | TEAM自体の監査機能（監査ログの閲覧）を利用する権限を持つ |
| 申請者 | Eligibility Policyに基づいて権限申請を行うことができる |
| 承認者 | Approver Policyに基づいて承認操作を行うことができる |

申請者と承認者のグループは複数用意でき、当社でも複数グループを利用しています。これについては、次に説明するEligibility PolicyやApprover Policyと合わせて説明します。

### TEAMで利用される各Policyの設定

TEAMにはEligibility PolicyとApprover Policyというものが存在します。それぞれ以下の役割です。

- Eligibility Policy
	- どのAWSアカウント（もしくはOU）に対して誰が **申請できるか** を設定する
- Approver Policy
	- どのAWSアカウント（もしくはOU）に対して誰が **承認できるか** を設定する

それぞれ、細かく設定もできますが、運用負担とのトレードオフです。当社では次に記載する方針としました。

#### Eligibility Policy

![Eligibility Policyのイメージ](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260625/20260625211757.png)

Eligibility Policyは1つだけ用意し、IAM Identity Centerで管理されている全社員がすべてのAWSアカウントへ申請できる構成としました。

セキュリティの観点では、役割ごとに申請可能なアカウントを絞り込む方が理想的です。しかし、そのためには「権限申請するための事前申請」が別途必要となり、運用負担が大きくなると判断しました。

**「申請の入口は広く、承認の出口は厳密に」** という方針のもと、誤った申請や不正な申請は後述するApprover Policyの承認者が拒否できるため、このトレードオフを意図的に選択しています。

#### Approver Policy

![Approver Policyのイメージ](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260625/20260625211804.png)

Approver PolicyはAWSアカウント単位で用意して、該当するAWSアカウントのJITアクセス承認者となるグループに関連付けます。

これによって、承認可能な人を厳密に制御できるためセキュリティが向上します。

なお、複数のApprover Policyを管理することが大変な場合には、OSSとしてTerraform Providerが公開されています。

<iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fregistry.terraform.io%2Fproviders%2Fawsteam-contrib%2Fawsteam%2Flatest%2Fdocs" title="Terraform Registry" frameborder="0"></iframe>[registry.terraform.io](https://registry.terraform.io/providers/awsteam-contrib/awsteam/latest/docs)

## 初回導入後の状況

ここまでご紹介した方針で、まずは一部の組織へ導入して問題がないことを確認しました。その上で、他の組織に対しても段階的に導入を進めました。

幸いにも大きな混乱が発生することはありませんでしたが、以下のような要望があがりました。

> 日常的な運用業務において読み取り専用のみでは不十分なケースがある。そのために都度JITアクセス申請するのは運用的に困難。

例えば、日常的な運用作業で必要となる一部の操作がReadOnlyAccessポリシーではカバーされていないケースがありました。

そこで、JITアクセスの例外として **必要最小限のポリシー** を持ったAWSアカウントごとに個別のPermission Setを作成できる仕組みを検討しました。

## AWSアカウントごとに個別のPermission Set

Permission Setの数が増えるということは、全社AWS管理部門の負担も増加します。また、個別の事情に応じてPermission Setを用意できるといっても、JITアクセスのメリットを損なうようでは意味がありません。

そこで以下を要件として仕組みを検討しました。

- AWSアカウント毎の個別要件に応じた権限を常時保有できること
- Permission Setの数が膨大になっても全社AWS管理部門の負担が増えすぎないようにすること
- 必要最小限の権限になっていることを仕組みで担保すること

これらの要件を満たすために検討したアーキテクチャは以下です。

![個別Permission Setのアーキテクチャ](https://cdn-ak.f.st-hatena.com/images/fotolife/v/vasilyjp/20260626/20260626220415.png)

全社AWS管理部門の負担を低減するために、Identity Centerの管理アカウント側では **Permission Setの箱だけを用意** します。ポリシーの中身については、 **メンバーアカウント側のカスタマー管理ポリシーで設定** してもらう方針としました。これによって、メンバーアカウント側で運用変更が発生しても、全社AWS管理部門側での作業は発生しません。

また、必要最小限の権限となっていることを担保するために、AWS Configを活用したガードレールを用意し、基準を満たさないポリシーを検知できる仕組みとしています。

なお、Permission Set数のクォータは以下の公式ドキュメントで説明されています。上限緩和も可能となっており、当社の規模では不足することはない想定です。

<iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fdocs.aws.amazon.com%2Fsinglesignon%2Flatest%2Fuserguide%2Flimits.html" title="Quotas and limits in IAM Identity Center - AWS IAM Identity Center" frameborder="0"></iframe>[docs.aws.amazon.com](https://docs.aws.amazon.com/singlesignon/latest/userguide/limits.html)

## まとめ

本記事では、JITアクセスの概念とTEAM選定の理由から、承認フローの設計、大規模組織での段階的展開における調整のポイント、導入後に発生した課題への対応までをご紹介しました。導入から1年以上が経過しましたが大きな問題なく運用が継続しています。セキュリティ向上のためにJITアクセスの導入を検討している方がいれば、ぜひ参考にしてみてください。今後もAWSを安全に運用するためにさまざまな取り組みを行っていこうと考えています。

ZOZOでは、一緒にサービスを作り上げてくれる方を募集中です。ご興味のある方は、以下のリンクからぜひご応募ください。

<iframe src="https://hatenablog-parts.com/embed?url=https%3A%2F%2Fcorp.zozo.com%2Frecruit%2F" title="採用 - 株式会社ZOZO" frameborder="0"></iframe>[corp.zozo.com](https://corp.zozo.com/recruit/)
