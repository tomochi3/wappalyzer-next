# Wappalyzer Next

[Wappalyzer](https://www.wappalyzer.com/) のブラウザ拡張機能とそのフィンガープリントを使って、Web サイトで使われている技術を検出するツールです。次の3通りの使い方ができます。

- **Chrome の拡張機能**として、開いているページを1つずつ調べる
- **コマンドラインツール**として、多数の URL をまとめて調べ、JSON / CSV / HTML で保存する
- **Python ライブラリ**として、自分のプログラムから呼び出す

公式のオープンソース版が終了した後に出てきた類似プロジェクトは、フィンガープリントが古く、動的な Web アプリでは精度が出ません。このプロジェクトは Playwright で Chromium を動かし、その中で拡張機能そのものを実行することで、この問題を解決しています。

![demo](https://github.com/user-attachments/assets/7a51b034-c9a7-44e6-aa80-2f8a23311e72)

- [Chrome の拡張機能として使う](#chrome-の拡張機能として使う)
- [インストール](#インストール)
- [コマンドラインでの使い方](#コマンドラインでの使い方)
- [セキュリティ](#セキュリティ)
- [開発者向け（Python ライブラリ）](#開発者向けpython-ライブラリ)
- [FAQ](#faq)

## Chrome の拡張機能として使う

Chrome 用に調整した Wappalyzer 拡張機能を同梱しています。元の拡張機能から次の点を変えています。

- インストール直後やアップデート時に wappalyzer.com のページが開く処理を取り除いています。
- 閲覧したサイトのホスト名と検出した技術を wappalyzer.com に送る機能を、初期状態でオフにしています。

1. 拡張機能をダウンロードします: **[wappalyzer-extension.zip](https://github.com/tomochi3/wappalyzer-next/raw/main/wappalyzer/data/wappalyzer-extension.zip)**（約35MB）
2. zip を任意のフォルダに展開します（例: `C:\tools\wappalyzer-ext`）。
3. Chrome のアドレスバーに `chrome://extensions` と入力して開きます。
4. 右上の「デベロッパー モード」をオンにします。
5. 「パッケージ化されていない拡張機能を読み込む」を押し、展開したフォルダ（`manifest.json` が直下にあるフォルダ）を選びます。
6. 調べたいサイトを開き、ツールバーの Wappalyzer アイコンをクリックすると、検出された技術が表示されます。

> [!IMPORTANT]
> 拡張機能の「オプション」にある「特定した技術を匿名でwappalyzer.comに送信する」は、オンにしないでください。オンにすると、閲覧したサイトのホスト名と検出した技術が wappalyzer.com に送信されます。社内サイトの名前も送られます。Chrome ウェブストアの公式版を使う場合は、この設定が初期状態でオンなので、チェックを外してください。

注意:

- この方法で入れた拡張機能は自動で更新されません。新しい版は、このリポジトリの zip が更新された後に、同じ手順で入れ直してください。
- デベロッパー モードは、会社のポリシーで禁止されていることがあります。社内 PC で使う前に、情報システム部門に確認してください。自動更新される署名付きの公式版が良い場合は、Chrome ウェブストアで「Wappalyzer」を検索して追加してください。
- 拡張機能で調べられるのは、開いているページ1つずつです。多数の URL をまとめて調べたり、結果をファイルに保存したりするには、次のコマンドラインツールを使ってください。
- 下の「[セキュリティ](#セキュリティ)」の対策はコマンドラインツールの機能です。拡張機能として使う場合には適用されません。

## インストール

> [!NOTE]
> PyPI の `wappalyzer` パッケージは元のプロジェクト（[s0md3v/wappalyzer-next](https://github.com/s0md3v/wappalyzer-next)）のもので、このリポジトリのセキュリティ修正は入っていません。このリポジトリからインストールしてください。

#### コマンドラインツールとしてインストール
```bash
pipx install git+https://github.com/tomochi3/wappalyzer-next.git
```
```bash
pipx run --spec playwright playwright install chromium
```

#### ライブラリとしてインストール
ライブラリとして使う場合は、`venv` や `docker` などの隔離した環境に `pip` でインストールしてください。`--break-system-packages` を付けて通常のインストールもできますが、おすすめしません。

```bash
pip install git+https://github.com/tomochi3/wappalyzer-next.git
```
```bash
python -m playwright install chromium
```

最小構成の Linux コンテナでは、Chromium が必要とするシステムライブラリも入れてください。

```bash
python -m playwright install-deps chromium
```

#### Docker でインストール
<details><summary>手順</summary>

1. リポジトリをクローンします。
```bash
git clone https://github.com/tomochi3/wappalyzer-next.git
```
```bash
cd wappalyzer-next
```

2. Docker Compose でビルドします。
```bash
docker compose build
```

3. コンテナで URL を調べます。

- 1つの URL を調べる:
```bash
docker compose run --rm wappalyzer -i https://example.com
```
- ファイルに書いた複数の URL を調べる:
```bash
docker compose run --rm wappalyzer -i urls.txt -w 3 -oJ output.json
```

コンテナは一般ユーザー（uid 1000）で動き、Chromium のサンドボックスも有効です。サンドボックスに必要な設定は `docker-compose.yml` に入っています。`docker run` で直接動かす場合は、次のように自分で指定してください。
```bash
docker run --rm --shm-size 2g --security-opt seccomp=docker/seccomp_profile.json --security-opt no-new-privileges:true --cap-drop ALL --cap-add SYS_CHROOT -v "$PWD:/app" wappalyzer -i https://example.com
```
出力ファイルはマウントしたディレクトリに uid 1000 として書き込まれるので、そのディレクトリは uid 1000 から書き込める必要があります。
</details>

## コマンドラインでの使い方
よく使う例です。すべてのオプションは下の一覧を参照してください。

| やりたいこと | コマンド |
|---|---|
| 1つの URL を調べる | `wappalyzer -i https://example.com` |
| ファイルに書いた複数の URL を調べる（1行に1つ） | `wappalyzer -i urls.txt -w 3` |
| タイムアウトを変える（秒） | `wappalyzer -i urls.txt -t 15` |
| ログインが必要なページを調べる | `wappalyzer -i https://example.com --cookie-file cookie.txt` |
| JSON で保存する | `wappalyzer -i https://example.com -oJ results.json` |
| JSON を標準出力に出す | `wappalyzer -i https://example.com -oJ` |
| CSV で保存する | `wappalyzer -i urls.txt -oC results.csv` |
| HTML レポートを作る（検索・絞り込みができる） | `wappalyzer -i urls.txt -oH report.html` |
| ブラウザを使わずに速く調べる（精度は下がる） | `wappalyzer -i urls.txt --scan-type fast` |

Cookie は環境変数 `WAPPALYZER_COOKIE` でも渡せます。`-c "sessionid=abc123"` と直接書くこともできますが、プロセス一覧やシェルの履歴に残ります。

出力オプションでファイル名を省略すると、結果は標準出力に書き出されます。進捗、バナー、エラーは標準エラーに出ます。

#### オプション一覧

> 精度を重視する場合は `full`（既定）を使ってください。`fast` と `balanced` はブラウザを使いません。

- `-i`: 調べる URL、または URL を1行に1つずつ書いたファイル
- `--scan-type`: スキャンの種類（既定: `full`）
  - `fast`: HTTP リクエストを1回だけ送る簡易スキャン
  - `balanced`: HTTP でさらにリクエストを送るスキャン
  - `full`: Wappalyzer 拡張機能を使う完全なスキャン
- `-w, --workers`: 同時に処理する数（既定: 5。`full` は最大3）
- `-t, --timeout`: ページの読み込みや HTTP レスポンスを待つ最大秒数（既定: 30）
- `-oJ [file]`: JSON の出力先。省略するか `-` にすると標準出力
- `-oC [file]`: CSV の出力先。省略するか `-` にすると標準出力
- `-oH [file]`: HTML レポートの出力先。省略するか `-` にすると標準出力
- `-c, --cookie`: ログインが必要なページ用の Cookie ヘッダー文字列
- `--cookie-file`: Cookie ヘッダー文字列をファイルから読む（どちらも指定しない場合は環境変数 `WAPPALYZER_COOKIE` を使う）
- `--insecure`: TLS 証明書を検証しない
- `--no-sandbox`: Chromium のサンドボックスを無効にする。隔離したコンテナの中でだけ使ってください。環境変数 `WAPPALYZER_NO_SANDBOX=1` でも同じです

## セキュリティ

コマンドラインツールとライブラリは、スキャンするサイトを信頼できないものとして扱います。

- Chromium はサンドボックスを有効にして動きます。そのため、`--no-sandbox` を付けない限り、root では `full` スキャンを実行しません。一般ユーザーで実行してください。
- 外部の公開サイトを調べているとき、そのページが社内アドレス・ループバック・リンクローカル（169.254.x.x など）に向けて出すリクエストは遮断します。対象はスクリプト、`fetch()`、WebSocket、HTTP スキャンでのリダイレクト、`robots.txt` です。悪意のあるページがツールを通して社内ネットワークに入り込むことを防ぎます。社内サイトを直接調べることは今までどおりできます。ただし、ブラウザ自身がたどるリダイレクトはチェックしていません。このリスクは、普通のブラウザでそのページを開いた場合と同じです。
- TLS 証明書を検証します。通信を検査する社内プロキシの環境で証明書エラーになる場合は、`--insecure` ではなく、環境変数 `REQUESTS_CA_BUNDLE` に会社の証明書ファイルを指定してください。
- HTTP レスポンスは 10MB まで、待ち時間は `-t` の秒数までです。
- URL ごとにブラウザのストレージ・Cookie・キャッシュを消し、ダウンロードは拒否します。
- 同梱の Wappalyzer 拡張機能が、スキャンしたホスト名を wappalyzer.com に送る機能を止めています。
- `balanced` スキャンの DNS の問い合わせは、固定の公開 DNS ではなく、PC に設定されている DNS を使います。
- スキャンしたページから取り出した値は、HTML レポートではエスケープします（Content-Security-Policy も付けています）。CSV では数式として実行されないようにし、ターミナルでは制御文字を取り除きます。

## 開発者向け（Python ライブラリ）

ライブラリは `wappalyzer` という名前で import できます。

#### ライブラリの使い方

複数の URL を調べるときは `Wappalyzer` を使います。ブラウザは1回だけ起動されて使い回され、`with` ブロックを抜けると閉じます。

```python
from wappalyzer import Wappalyzer

with Wappalyzer(workers=3, timeout=30) as scanner:
    results = scanner.analyze_many([
        'https://example.com',
        'https://github.com',
        'https://python.org',
    ])

for url, technologies in results.items():
    print(url)
    for name, data in technologies.items():
        version = f" {data['version']}" if data['version'] else ""
        print(f"  {name}{version}")
```

同じスキャナーで、Chromium を開き直さずに1つずつ調べることもできます。

```python
from wappalyzer import Wappalyzer

with Wappalyzer(workers=3, timeout=30) as scanner:
    github = scanner.analyze('https://github.com')
    python = scanner.analyze('https://python.org')
```

URL が1つだけなら `analyze()` が手軽です。スキャナーを作り、1回スキャンして閉じます。

```python
from wappalyzer import analyze

results = analyze(
    url='https://example.com',
    scan_type='full',  # 'fast'、'balanced'、'full' のいずれか
    cookie='sessionid=abc123',
    timeout=30
)
```

大量の URL を調べるときに、トップレベルの `analyze()` をループで呼ばないでください。URL ごとに Chromium と拡張機能が読み込み直されます。`Wappalyzer.analyze_many()` を使うか、使い回すスキャナーで `Wappalyzer.analyze()` を呼んでください。

#### analyze() の引数

- `url` (str): 調べる URL
- `scan_type` (str, 省略可): スキャンの種類
  - `'fast'`: HTTP の簡易スキャン
  - `'balanced'`: HTTP でさらにリクエストを送るスキャン
  - `'full'`: JavaScript の実行も含む完全なスキャン（既定）
- `workers` (int, 省略可): `full` スキャンで作るブラウザの数（既定: 1）
- `cookie` (str, 省略可): ログインが必要なページ用の Cookie ヘッダー文字列
- `timeout` (int, 省略可): ページの読み込みや HTTP レスポンスを待つ最大秒数（既定: 30）
- `sandbox` (bool, 省略可): Chromium をサンドボックス付きで動かす（既定: True）。root 以外のユーザーで実行する必要があります
- `insecure` (bool, 省略可): TLS 証明書を検証しない（既定: False）

#### 戻り値

URL をキー、検出した技術を値とする辞書を返します。

```json
{
  "https://github.com": {
    "Amazon S3": {
      "version": "",
      "confidence": 100,
      "categories": ["CDN"],
      "groups": ["Servers"]
    },
    "React Router": {
      "version": "6",
      "confidence": 100,
      "categories": ["JavaScript frameworks"],
      "groups": ["Web development"]
    }
  },
  "https://example.com": {}
}
```

## FAQ

#### なぜ Chromium と Playwright を使うのですか？
`full` スキャンは、Playwright で動かす Chromium の中で Wappalyzer 拡張機能を実行します。Playwright は Chromium の拡張機能を直接扱えるので、geckodriver や Selenium が要りません。

#### `fast`、`balanced`、`full` の違いは？
- **fast**: URL に HTTP リクエストを1回だけ送ります。拡張機能は使いません。
- **balanced**: さらに .js ファイルや /robots.txt にリクエストを送り、DNS も問い合わせます。拡張機能は使いません。
- **full**: 公式の Wappalyzer 拡張機能を使い、ヘッドレスブラウザで URL を調べます。
