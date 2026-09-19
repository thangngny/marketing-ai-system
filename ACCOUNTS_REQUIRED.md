# Tài khoản và credential cần chuẩn bị

Không điền secret vào Git. Tạo `C:\Users\Admin\marketing-ai-system\.env.local` từ `.env.example`, chỉ điền giá trị trên máy này, rồi giữ file đó ngoài Git. Lệnh kiểm tra chung:

```powershell
cd C:\Users\Admin\marketing-ai-system
.\scripts\doctor.ps1
```

## Hai việc bắt buộc cho Buzz → Hermes

### Hermes provider

- Cần: một provider/model được Hermes hỗ trợ. Hiện profile `marketing` chưa đăng nhập provider nào.
- Thực hiện: `hermes -p marketing model` và hoàn tất đăng nhập/nhập API key theo màn hình chính thức.
- Kiểm tra:

```powershell
hermes -p marketing -z "Reply exactly: MARKETING_ORCHESTRATOR_OK"
```

Kỳ vọng: `MARKETING_ORCHESTRATOR_OK`. Không tiếp tục coi Buzz live nếu lệnh này còn báo `not connected to any AI provider`.

### Buzz identity

- Cần: một Nostr identity riêng cho Marketing Orchestrator, đã là member của community và channel thử nghiệm.
- Cần từ owner: channel UUID và npub của chính owner để lập allowlist.
- Không dùng private key của user làm key agent.
- Sau khi identity đã được tạo/thêm vào channel:

```powershell
.\scripts\configure-buzz.ps1 -ChannelId "<channel-uuid>"
```

Script hỏi private key bằng trường nhập ẩn; không in key ra màn hình. Trên máy hiện tại, script có thể tái sử dụng duy nhất owner allowlist đã có trong Buzz Desktop; truyền `-OwnerNpub` nếu muốn chỉ định khác.

## Zoho CRM

- Tài khoản: Zoho CRM organization (production hoặc sandbox/developer đúng môi trường cần dùng).
- Tạo: server-based OAuth client trong Zoho API Console.
- Quyền ban đầu: chỉ READ cho Leads, Contacts, Accounts, Deals, Tasks; thêm CREATE/UPDATE sau khi quy trình duyệt đã được chấp nhận. Không cấp DELETE trong Phase 1.
- Điền: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, đúng accounts/API domain theo data center.
- Kiểm tra không phá dữ liệu:

```powershell
uv run marketing-system connector zoho --live
```

Probe chỉ đổi refresh token thành access token rồi đọc organization; không tạo/sửa CRM.

## Microsoft 365 / Microsoft Graph

- Tài khoản: Microsoft 365 tenant và user được phép đọc đúng mailbox/calendar/files.
- Tạo: app registration trong Microsoft Entra ID; dùng delegated OAuth.
- Quyền khởi đầu: `User.Read`, `Mail.Read`, `Calendars.Read`, `Files.Read`, `Sites.Read.All` chỉ khi thực sự cần SharePoint. `Mail.ReadWrite` chỉ cần nếu tạo draft trên mailbox. Không xin `Mail.Send` trong Phase 1.
- Điền: `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` nếu app loại confidential, và access token OAuth vào `MS_GRAPH_ACCESS_TOKEN` cho lần kiểm tra.
- Kiểm tra:

```powershell
uv run marketing-system connector m365 --live
```

Probe chỉ gọi Graph `/me`.

## Apollo

- Tài khoản: Apollo account; một số endpoint yêu cầu work email và giới hạn tùy plan.
- Tạo: API key trong Apollo settings.
- Quyền: API key chỉ cho workspace cần dùng.
- Điền: `APOLLO_API_KEY`.
- Kiểm tra không tốn enrichment credit:

```powershell
uv run marketing-system connector apollo --live
```

Probe chỉ gọi `/auth/health`. People search hiện được tài liệu Apollo ghi 0 credits; organization search/enrichment có thể tốn credits và không chạy trong doctor.

## LinkedIn

- Tài khoản: LinkedIn member, LinkedIn Page nếu làm việc với page, và Developer app.
- Tạo: LinkedIn Developer application gắn với Page.
- Quyền: OpenID/profile cho nhận dạng; `w_member_social` nếu sau này đăng thay member. Community Management/Advertising cần đăng ký product và có thể cần LinkedIn phê duyệt. Chỉ xin scope đúng use case.
- Điền: `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_REDIRECT_URI`.
- Kiểm tra:

```powershell
uv run marketing-system connector linkedin --live
```

Probe chỉ đọc `userinfo`. Publishing vẫn bị khóa ở Phase 1.

## YouTube

- Tài khoản: Google Account, Google Cloud project, và YouTube channel nếu cần dữ liệu riêng.
- Tạo: bật YouTube Data API v3; tạo API key giới hạn theo API/IP cho đọc public. Tạo OAuth client nếu cần private data/analytics/upload.
- Quyền: bắt đầu với `youtube.readonly`; `youtube.upload` chỉ khi owner chủ động bật workflow upload sau này.
- Điền: `YOUTUBE_API_KEY`; OAuth dùng `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` khi cần.
- Kiểm tra:

```powershell
uv run marketing-system connector youtube --live
```

Probe đọc một video public và có tiêu thụ quota tối thiểu; không upload.

## Meta / Facebook Ads

- Tài khoản: Meta Developer account, Business Manager, app, và ad account owner cho phép truy cập.
- Tạo: Meta app có Marketing API; tạo user/system-user access token theo mô hình vận hành chính thức.
- Quyền ban đầu: `ads_read`. Chưa xin/dùng `ads_management` cho tới khi quy trình duyệt write được mở.
- Điền: `META_APP_ID`, `META_APP_SECRET`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`.
- Kiểm tra:

```powershell
uv run marketing-system connector meta_ads --live
```

Probe chỉ đọc id/name/status của ad account. Không tạo campaign và không chi tiền.

## Google Ads

- Tài khoản: Google Ads manager/client account và Google Cloud OAuth client.
- Tạo: developer token trong Google Ads API Center; OAuth consent/client; refresh token có scope `https://www.googleapis.com/auth/adwords`.
- Điền: `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`; thêm `GOOGLE_ADS_LOGIN_CUSTOMER_ID` khi đi qua manager account.
- Kiểm tra:

```powershell
uv run marketing-system connector google_ads --live
```

Probe chỉ gọi `customers:listAccessibleCustomers`. Mọi mutate/budget operation bị khóa.

## Website

- Tài khoản: không bắt buộc cho trang public. Nếu CMS có API, sẽ cần tài khoản riêng theo CMS sau khi biết nền tảng.
- Điền: `WEBSITE_URL`; tạo `WEBSITE_WEBHOOK_SECRET` ngẫu nhiên khi bật form webhook.
- Quyền: read-only/public metadata trước; CMS write không bật trong Phase 1.
- Kiểm tra:

```powershell
uv run marketing-system connector website --live
```

Probe chỉ GET URL và theo redirect; không sửa website.
