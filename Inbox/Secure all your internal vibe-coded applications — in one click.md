https://blog.cloudflare.com/workers-protected-by-access/
# Secure all your internal vibe-coded applications — in one click
2026-08-16
AI has enabled employees across every team to build applications faster than ever before.

But that speed is also what's keeping every CISO up at night: any employee can build an application, deploy it to the public Internet, and accidentally expose internal work or company data.

Today, we're launching new tools to make it easy to keep your applications hosted on Workers private. You can now apply Cloudflare Access directly to a Worker or to every Worker in your account, so that your applications are behind your company login by default, without relying on each developer to set that up themselves.

You can now:

- **Set a policy at the account level** to ensure that all [preview](https://developers.cloudflare.com/pages/configuration/preview-deployments/) and production deployments are behind your company login by default.
- **Set a policy on a single application** to ensure authentication is enforced on every domain associated with it, no matter how it's deployed.
- **See exactly who visits your application.** Get every authenticated user’s email, name, and groups directly in your code — no JWT (JSON Web Token) validation required.
- **Deploy an internal platform where every deployment is private by default.** We've open-sourced an [example](https://github.com/cloudflare/templates/tree/main/internal-sites-template): an internal static site platform where every Worker deployed is private.

## Access on Workers: how it works

When you enable Access on a Worker, Cloudflare enforces authentication before any request reaches your application code. It doesn't matter how the request gets to your Worker, whether it's through a custom domain, a route, a workers.dev subdomain, or a preview URL. If Access is on, the user has to authenticate first.

![BLOG-3405 2.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW0HX4DTD6BC7S3Q2H5AXH6.png&w=1430&h=394&f=webp&fit=cover&position=center)

BLOG-3405 2.png

Previously, you had to configure this at the hostname level, which meant setting up Access policies on each domain your Worker was reachable on. If you wanted to add a new custom domain to your Worker, you needed to update the Access policy first or that hostname would be reachable without authentication.  
Now the policy is attached to the Worker itself, so any domain or URL associated with that Worker is automatically protected. You can choose what to protect: just preview URLs, or all hostnames.

If you set it to previews only, every preview URL created for that application, whether it's a [workers.dev](http://workers.dev/) preview URL or a custom domain you use for previews, will require authentication whenever you deploy a new version. If you set it to all hostnames, every domain associated with that Worker is protected — custom domains, routes, [workers.dev](http://workers.dev/) subdomains, and preview URLs.

Access gives you control over how users authenticate. You can connect your existing identity provider, so employees sign in with the credentials they already use, or restrict access to specific email addresses, email domains, or groups. For agents, you can grant access through service tokens.

Read more in the [Cloudflare Access for Workers documentation](http://developers.cloudflare.com/workers/configuration/cloudflare-access/) here.

## Keep every Worker in your account private by default

If you have developers across your organization deploying Workers, you don't want to rely on each one to remember to enable Access. You want the default to be private.

You can set an Access policy once at the account level, and every Worker in your account, current and future, is private from the moment it's created.

You choose what the policy covers: only preview URL traffic, all production traffic, or both. Preview-only is useful if your production Workers are intentionally public, but you never want an in-progress deployment exposed.

![BLOG-3405 3.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW0HX9XADQQ6XGNZ2XGEWT0.png&w=1430&h=1352&f=webp&fit=cover&position=center)

BLOG-3405 3.png

Need a Worker to be public? Bypass the account-wide policy on that one Worker.

![BLOG-3405 4.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW0HXBJ3AC63FWYT3SDAZQ5.png&w=1430&h=886&f=webp&fit=cover&position=center)

BLOG-3405 4.png

### Protect a specific Worker

If you don't need an account-wide default and just want to lock down one specific Worker, you can apply Access to that Worker directly.

![BLOG-3405 5.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW174EPXAKWHWVAHM6NHZJY.png&w=1430&h=1332&f=webp&fit=cover&position=center)

BLOG-3405 5.png

The new Access tab in the Worker view shows exactly which policies apply to that application. If you have multiple, the most specific one takes priority: hostname policies first, then Worker policies, then account policies.

## See who is accessing your application

When Access is protecting your Worker, you can get information about who is making each request — their email, name, and groups — so you can personalize what they see, enforce permissions, or log activity per user.

This works through your [Worker's context object (ctx)](https://developers.cloudflare.com/workers/runtime-apis/context/). Every request to your Worker carries a ctx with metadata about that request. When Access is enabled, we attach the authenticated user's identity to it as ctx.access. From there, call `ctx.access.getIdentity()` to get back the user's email, name, and [more](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/).

Before, this meant validating a JWT yourself — parsing the token, verifying the signature, and extracting the claims. Now, when Access is enabled on your Worker, every authenticated request includes ctx.access.

Here's all you need to get the user's identity:

```
export default {
  async fetch(request, env, ctx) {
    if (!ctx.access) {
      return new Response("Access required", { status: 403 });
    }

    const identity = await ctx.access.getIdentity();
    const email = identity?.email ?? "unknown";

    return new Response(\`Hello, ${email}\`);
  }
};
```

## Test locally before you deploy

We showed how you can use `ctx.access.getIdentity()` to give your Worker information about who is making a request — their email, name, and groups.

You can use this when developing locally with wrangler dev. Add an access block to your `wrangler.jsonc` to simulate an authenticated user:

```
{
  "access": {
    "dev": {
      "aud": "my-app",
      "identity": { "email": "admin@company.com" }
    }
  }
}
```

Your Worker picks it up through `ctx.access.getIdentity()` — returning an identity object shaped like what you'd get in production. Swap the email in your config to test as a different user.

This means you can verify that the right content shows up for the right user without having to deploy and sign in through Access every time you make a change.

## Deploy an internal platform where every application is private by default

If you manage an internal platform where employees can prototype and deploy applications, you need every application to be private without configuring access controls on each one.

[Workers for Platforms](https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/) lets you deploy Workers at scale. Every Worker lives inside a namespace, and all traffic to that namespace goes through a single entry point: the dispatch Worker.

Set an Access policy on your dispatch Worker, and every Worker deployed through it is private by default.

![BLOG-3405 6.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW0HX0D898RCER0VGF06TWR.png&w=1430&h=602&f=webp&fit=cover&position=center)

BLOG-3405 6.png

We also have an [open-source example](https://github.com/cloudflare/templates/tree/main/internal-sites-template) where you can deploy your own internal drag-and-drop deployment platform — configure access on the dispatcher worker once and every site deployed through it is private by default.

Click the button below to deploy it yourself!

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/cloudflare/templates/tree/main/internal-sites-template)

![BLOG-3405 7.png](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZW0HX50YD736BDZ9D4PPFR5.png&w=1430&h=520&f=webp&fit=cover&position=center)

BLOG-3405 7.png

For the full architecture, see our [Workers for Platforms reference architecture.](https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/)

## Built on solid foundations

This feature was made possible by FL2, the new [Rust-based modular proxy](https://blog.cloudflare.com/20-percent-internet-upgrade/) that powers Cloudflare's edge. Access is the front gate to your applications, and as such, it traditionally ran before all Workers logic in the request pipeline. But in order for Access applications to target individual Workers themselves instead of their hostnames, Access needs to know which Worker a given request is destined to reach. Therefore, we needed to split Workers *routing* from Workers *execution*, and move the routing logic, so it could run before Access.

In our old FL1 system based on NGINX and modules written in Lua, this change would have been complex and risky. Interactions between products can be subtle, and moving logic to an earlier phase of the request pipeline can be unsafe if it depends on shared state that is modified by another product.

FL2 made it easy. Its strict module system separates logic into well-defined, consistently ordered phases that statically declare their inputs and outputs. We were able to lean on the compiler to surface any broken interactions between phases, and gradually roll out this refactor with confidence.

## Try it today

This is now available to everyone. Try it out in the [dashboard](https://dash.cloudflare.com/account/workers-and-pages) or read the [Cloudflare Access for Workers documentation](http://developers.cloudflare.com/workers/configuration/cloudflare-access/) to get started.

## Acknowledgments

Thank you to Jesse Li, Brandon Strittmatter, Kyle Hiller, Kenny Johnson, Matt "TK" Taylor, Brendan Irvine-Broque, Yomna Shousha, and Mike Aizatsky for the engineering and design work that made this possible!