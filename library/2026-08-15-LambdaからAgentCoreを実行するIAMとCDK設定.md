---
title: LambdaからAgentCoreを実行するIAMとCDK設定
url: https://wp-kyoto.net/configure-iam-polify-to-exec-agentcore-runtime/?utm_source=x&utm_medium=social&utm_campaign=blog-sns-automation&utm_content=configure-iam-polify-to-exec-agentcore-runtime
created: '2026-08-15T23:07:33'
type: article
tags:
- aws
- iam
- lambda
- cdk
- bedrock
summary: 'AWS LambdaからBedrock AgentCoreを実行するIAMポリシー設定を解説。

  実行権限としてInvokeAgentRuntimeの許可と2種類のリソースARN指定が必要。

  AWS CDKを用いた具体的なポリシー付与コード例も紹介している。'
read: false
shelf_life: medium
published_at: '2025-09-14'
---

# AWS Lambda から AgentCore を実行する際の IAM ポリシー設定と CDK での設定方法
2026-08-15
最終更新日: 2025年9月14日

AWS Lambdaから Amazon Bedrock AgentCoreを実行するために必要なIAMポリシー設定を解説。特に「bedrock-agentcore:InvokeAgentRuntime」権限と、正しいリソースARN指定のポイントをCDKでの実装例とともに紹介。

広告ここから

広告ここまで

AWS Lambda 関数から Amazon Bedrock AgentCore を実行するためには、当然ですが IAM ポリシーによる許可が必要です。この記事では。どのようなポリシーを設定すればよいかや、権限が漏れている場合に発生するエラーについて簡単にまとめました。

## 権限を設定しないと発生するエラー

AgentCore Runtimeでデプロイしたアプリを Lambda などで呼び出すと、次のようなエラーが出ます。

```
AccessDeniedException: User: arn:aws:sts::012345:assumed-role/ChatAgent-Y3TIbUItr5gx/hatAgent-Y3TIbUItr5gx is not authorized to perform: bedrock-agentcore:InvokeAgentRuntime on resource: arn:aws:bedrock-agentcore:us-east-1:012345:runtime/helpdeskagent-EmdlveFTRi because no identity-based policy allows the bedrock-agentcore:InvokeAgentRuntime action
```

AgentCore Runtime を実行するには、 `InvokeAgentRuntime` が必要なことがわかります。

## Bedrock AgentCore の実行権限を設定する際の注意点

`bedrock-agentcore:InvokeAgentRuntime` を許可する必要があることは、エラーメッセージからわかりました。ここでポリシーを設定する際に注意したい点がリソース ARN です。通常、 Runtimeのリソース ARN を指定すると、以下ような構成になるはずです。

```
arn:aws:bedrock-agentcore:{region}:{account-id}:runtime/{agent-id}
```

AgentCore Runtimeを実行するには、もう1つリソース ARN の指定が必要です。それはAgentCore Runtimeのエンドポイントに関する ARN です。

```
arn:aws:bedrock-agentcore:{region}:{account-id}:runtime/{agent-id}/runtime-endpoint/*
```

この2つをリソース ARNとして指定することで、 Lambda などの AWS リソースから AgentCore Runtimeを実行できるようになります。

### CDK で実装する場合

CDK でポリシーを設定する場合、 Runtime の ARN を定数的に定義しておくと便利です。Runtime と Runtime のエンドポイントの ARN の2つを指定する必要があるため、先に定義しておくことで、何回も ARN を指定する必要がなくなります。

```
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';

// Bedrock Agent Runtime ARN を設定
const bedrockAgentRuntimeArn = 
  props.bedrockAgentRuntimeArn || 
  \`arn:aws:bedrock-agentcore:us-east-1:${this.account}:runtime/xxxxx\`;
```

次に、Lambda 関数に必要な権限を付与していきます。

```
// Lambda 関数に Bedrock Agent Runtime の実行権限を付与
lambdaResource.addToRolePolicy(
  new PolicyStatement({
    effect: Effect.ALLOW,
    actions: ['bedrock-agentcore:InvokeAgentRuntime'],
    resources: [
      bedrockAgentRuntimeArn,
      \`${bedrockAgentRuntimeArn}/runtime-endpoint/*\`
    ],
  })
);
```

Node.jsを実行する Lambda であれば、こんな感じになるかと思います。

```
const lambdaResource = new NodejsFunction(
  this,
  'example',
  {
    entry: 'lambda/handler.ts',
    handler: 'handler',
    runtime: Runtime.NODEJS_22_X,
    memorySize: 512,
    environment: {
      BEDROCK_AGENT_RUNTIME_ARN: bedrockAgentRuntimeArn,
    },
  }
);

// SSM パラメータストアへの読み取り権限
hubspotApiKey.grantRead(lambdaResource);

// Bedrock Agent Runtime の実行権限を付与
lambdaResource.addToRolePolicy(
  new PolicyStatement({
    effect: Effect.ALLOW,
    actions: ['bedrock-agentcore:InvokeAgentRuntime'],
    resources: [bedrockAgentRuntimeArn, \`${bedrockAgentRuntimeArn}/runtime-endpoint/*\`],
  })
);
```

## まとめ

AWS Lambda から Bedrock AgentCore を実行するためには、 `bedrock-agentcore:InvokeAgentRuntime` アクションを許可する iAM ポリシーを設定しましょう。また、リソース ARN では、 `/runtime-endpoint` を含むリソース ARN の指定も忘れないようにしましょう。
