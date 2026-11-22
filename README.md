# wa2html

**[English](#en)** · [Español](#es) · [Português](#pt) · [Français](#fr) · [Deutsch](#de) · [Italiano](#it)

[![Latest release](https://img.shields.io/github/v/release/EnriqueWood/wa2html?label=download)](https://github.com/EnriqueWood/wa2html/releases/latest)
[![CI](https://github.com/EnriqueWood/wa2html/actions/workflows/ci.yml/badge.svg)](https://github.com/EnriqueWood/wa2html/actions/workflows/ci.yml)

**Download:** <https://github.com/EnriqueWood/wa2html/releases/latest>

<a name="en"></a>
## English

wa2html turns a WhatsApp chat export into **one HTML file that looks and works like WhatsApp**:
voice notes play right in the browser, photos, stickers and videos appear in the conversation, and
you can search, jump to a date and change the wallpaper and colours. It needs no app, no account
and no internet connection, so the conversation stays readable for years.

It was written to keep chats that matter, such as the conversation with a loved one who is no
longer here.

- **Nothing is lost.** Every line of the chat transcript is accounted for, every file of the export
  is embedded (or copied) byte for byte, and the original transcript travels inside the page. After
  writing the page, wa2html reads it back and checks all of this with SHA-256 checksums.
- **Nothing leaves your computer.** wa2html works offline, and the page it creates is locked so it
  cannot load anything from the internet.
- **In your language.** The program and the page speak English, Spanish, Portuguese, French,
  German and Italian.
- **Free and open source** (MIT licence).

> wa2html is an independent project. It is not affiliated with, or endorsed by, WhatsApp or Meta.

### Download

Get the program for your computer from the **[latest release](https://github.com/EnriqueWood/wa2html/releases/latest)**:

| Computer | File |
| --- | --- |
| Windows 10/11 (64-bit) | `wa2html-windows-x64.exe` |
| Windows, for terminals and scripts | `wa2html-cli-windows-x64.exe` |
| Mac with Apple silicon (M1 or newer) | `wa2html-macos-arm64` |
| Linux (64-bit) | `wa2html-linux-x64` |

The release also has `SHA256SUMS.txt`, with the checksum of each file. Intel Macs and other
systems can run wa2html with Python (see [With Python](#en-python)).

### Step 1: export the chat from WhatsApp

These steps follow WhatsApp's help page
[How to export your chat history](https://faq.whatsapp.com/1180414079177245/).

**Before you start:** scroll through the whole chat on the phone and tap every photo, video or
voice message that still shows a download button. WhatsApp only exports media that is stored on the
phone; for the rest the transcript just says something like `image omitted`.

**Android**

1. Open the individual or group chat.
2. Tap **⋮** (More options) > **More** > **Export chat**.
3. Tap **Include media**.
4. Choose how to send it (for example Quick Share, Gmail or Chat) and get the files to your
   computer. Depending on the phone you get a `.zip` file, or a `.txt` file plus the media files;
   in the second case put them all in one folder.

**iPhone**

1. Open the individual or group chat.
2. Tap the contact's or group's name > **Export chat**.
3. Choose **With all media**.
4. Choose how to send it (for example Save to Files) and copy the `.zip` file to your computer.

Good to know, from WhatsApp's help page:

- On iPhone, view-once messages are not exported.
- On Android, **Include media** attaches *the most recent* media. In a long chat, check that the
  period shown by wa2html starts where the chat starts on the phone.
- An export cannot be imported back into WhatsApp: it is a copy for reading, not a backup. Keep
  your WhatsApp backup as well, and keep the original `.zip` in more than one safe place.

### Step 2: turn it into a page

Open wa2html. A window shows three steps:

1. **Exported chat:** choose the `.zip` (or, for Android exports without a zip, the folder with the
   files). wa2html shows how many messages and files it found.
2. **Options:** whose messages go on the right, optional photos of the contact and of you (each
   one appears in that person's voice messages; the contact's also in the header; wa2html
   remembers yours), one `.html` file or a folder with the media (for very large chats), and where
   to save it.
3. **Create page:** wa2html writes the page next to the `.zip` and checks it. When it says
   **Done. Checked: every message and file is in the page**, click **Open page**.

The language of the window can be changed at the top right; wa2html remembers it.

**Windows:** double-click `wa2html-windows-x64.exe`, or drag the `.zip` onto it to open the window
with the chat already chosen. The program is not signed, so Windows may say it protected your PC:
click **More info** > **Run anyway**.

**Mac** (the first time, in Terminal, in the folder where you downloaded it):

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # the program is not signed by Apple
./wa2html-macos-arm64                                # opens the window
```

After that you can also double-click it in Finder (a Terminal window opens beside wa2html).

**Linux:** `chmod +x wa2html-linux-x64`, then `./wa2html-linux-x64` opens the window.

<a name="en-python"></a>
**With Python** (any system with Python 3.10 or newer):

```sh
pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip
wa2html-gui                              # the window
wa2html "WhatsApp Chat - Alice.zip"      # or the command line
```

On Linux the window needs Tk for Python (for example `sudo apt install python3-tk`).

To keep the page, copy it together with the original `.zip`.

### Command line

The same conversion works without the window: `wa2html "WhatsApp Chat - Alice.zip"` (on Windows,
`wa2html-cli-windows-x64.exe "WhatsApp Chat - Alice.zip"`). It prints a report like this:

```
Source        WhatsApp Chat - Alice.zip
Transcript    _chat.txt: 2,310 lines, ios layout, day-first dates, 12-hour clock
Messages      2,041 (+2 WhatsApp notices); every line of the transcript is accounted for
Period        2024-03-02 09:12 -> 2025-08-17 21:40
Participants  Alice (1,130), Me (911)
Shown right   Me  [the participant the chat is not named after]
Attachments   164 mentioned, 164 found, 0 missing
              in the export: 88 image, 41 sticker, 27 voice, 5 video, 2 lottie, 1 document
Not exported  12 image, 1 video  (WhatsApp wrote 'omitted': the file was not on the phone when exporting)
Written       WhatsApp Chat - Alice.html (131.6 MB)
Verified      all 2,043 messages, the original transcript and 164 files are in the result, identical to the export
```

If the last line says `verification FAILED`, do not rely on that page and keep using the `.zip`.
The window shows the same report under *Technical details*.

```
wa2html INPUT [-o OUTPUT] [--mode single|folder] [--check] [--force] [--no-verify] [--gui]
              [--me NAME] [--title TITLE] [--date-order auto|dmy|mdy|ymd]
              [--lang auto|en|es|pt|fr|de|it] [--theme auto|light|dark] [--time-format auto|12|24]
              [--wallpaper COLOUR] [--wallpaper-image IMAGE] [--no-pattern]
              [--avatar IMAGE] [--my-avatar IMAGE] [--lottie-js FILE]
```

- `INPUT`: the `.zip`, the folder with the exported files, or just the `.txt` (an export without
  media). It is only read, never changed.
- `--check`: print the report and write nothing.
- `--mode folder`: write `index.html` plus a `media/` folder with a copy of every file, instead of
  one big file. Better for very large chats: browsers get slow with HTML files of several hundred MB.
- `--me NAME`: whose messages go on the right. By default wa2html works it out (a one-to-one export
  is named after the other person); it can also be changed in the page.
- `--lang`: the page's default language. By default the page follows the reader's browser; the
  reader can always change it in the page.
- `--avatar IMAGE`: the contact's picture, for the chat header and their voice messages.
  `--my-avatar IMAGE`: your picture, for your voice messages. Without a picture a person's voice
  messages show their initials. `--wallpaper-image IMAGE`: a default wallpaper.
- `--gui`: open the window instead (with `INPUT` already chosen, if given).
- `-o OUTPUT`: where to write. Existing files are never overwritten: without `-o`, a new name such as
  `... (2).html` is used; with `-o`, wa2html stops unless you add `--force`.

### What the page shows

| In the chat | In the page |
| --- | --- |
| Text with `*bold*`, `_italic_`, `~strike~`, `` ```code``` ``, links | Formatted the same way; links open in a new tab |
| Voice messages | WhatsApp-style player: waveform, seek, 1× / 1.5× / 2×, plays the next voice message automatically |
| Photos | In the conversation; click for full screen (arrow keys move between photos) |
| Videos and GIFs | Players in the conversation |
| Stickers, including animated ones | Without a bubble, like WhatsApp |
| Documents and contacts | Cards with a download button |
| Calls and locations | Call bubbles (missed calls in red) and a map card with the coordinates |
| Deleted and edited messages | "This message was deleted" and an "Edited" label |
| Media WhatsApp left out | A note saying the file was not included in the export |
| Files no message mentions | Listed at the end, so nothing is hidden |

The **Appearance** panel (palette icon) changes the theme (light, dark or the system's), the
wallpaper (colours, gradients, a doodle pattern or a picture of your own), bubble colours, text size,
12/24-hour time, the language and whose messages appear on the right. Choices are remembered by the
browser. **Chat info** shows statistics and lets you download the original transcript. The page
also prints well (for example to PDF).

### Supported exports and limits

- Exports from iPhone (`[27-10-26, 11:55:22 AM] Name: text`) and Android
  (`27/10/26, 11:55 - Name: text`), in any date order and with a 12 or 24-hour clock: the layout is
  detected from the file. Messages that someone copied and pasted into a message stay inside it.
- WhatsApp's own texts (calls, "omitted", "deleted", "edited"...) are recognised in English and
  Spanish, and partly in Portuguese and other languages. Anything not recognised is still shown as
  text.
- One-to-one and group chats.
- Exports contain no replies (quoted messages), reactions, read receipts or profile pictures, so the
  page cannot show them.
- Tested in Microsoft Edge (Chromium), opening the page directly from disk. Chrome and Firefox play
  WhatsApp voice messages (Opus); Safari depends on its version and has not been tested.

### Animated stickers

Animated `.webp` stickers play natively in the browser. WhatsApp's own animated stickers (`.was`
files) are [Lottie](https://airbnb.io/lottie/) animations; wa2html bundles the "light" build of
[lottie-web](https://github.com/airbnb/lottie-web) 5.12.2 (MIT licence, 168 KB, in
`wa2html/assets/vendor/`) and adds it only to pages that contain such stickers. The light build has no
support for Lottie expressions; for a sticker that needs them, pass the full player with
`--lottie-js lottie_svg.min.js`.

### Translations

Every text of the window and of the page lives in `wa2html/locales/<language>.json`. To add a
language, copy `en.json` to, say, `nl.json`, translate the values (keep the `{placeholders}`) and run
the tests: they check that every language has every text. Corrections from native speakers are very
welcome.

### Development

```sh
git clone https://github.com/EnriqueWood/wa2html
cd wa2html
python -m unittest discover -s tests -t .   # tests, no dependencies (window tests need a display)
python -m wa2html --gui                      # the window, from the source
python -m wa2html --help                     # the command line
```

The tests build synthetic exports (made-up names, generated images and audio) for both platforms.
**Never commit real chats**: `.gitignore` excludes zips, generated pages and media files.

| Path | Contents |
| --- | --- |
| `wa2html/source.py` | Reading the zip, folder or `.txt` |
| `wa2html/parser.py` | Detecting the transcript layout and splitting it into messages |
| `wa2html/chat.py` | Classifying messages and media, participants |
| `wa2html/probe.py` | Image/video sizes, voice-message duration and waveform, without dependencies |
| `wa2html/render.py`, `wa2html/assets/` | The page (template, CSS, JavaScript) |
| `wa2html/verify.py` | The check after writing |
| `wa2html/convert.py` | The conversion, shared by the window and the command line |
| `wa2html/gui.py`, `wa2html/icon.py` | The window (Tkinter) and its icon |
| `wa2html/i18n.py`, `wa2html/locales/` | Translations |
| `packaging/` | Entry points, icon and smoke test for the standalone executables |
| `.github/workflows/` | CI (tests on Windows, Linux, macOS) and releases |

### Releases

The executables are built by GitHub Actions with PyInstaller (`.github/workflows/release.yml`):

1. Set the new version in `wa2html/__init__.py` (`__version__ = "0.2.0"`) and commit.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
3. The workflow runs the tests, builds the four executables, runs each one on a synthetic export,
   window included (`packaging/smoke_test.py`), and publishes a release with the executables and
   `SHA256SUMS.txt`. It stops if the tag does not match `__version__`.

Running the workflow by hand (Actions > Release > Run workflow) only builds and tests the
executables and keeps them as workflow artifacts.

### Licence

MIT. The bundled lottie-web player is © 2015 Bodymovin, also under the MIT licence
(`wa2html/assets/vendor/LICENSE-lottie-web.md`).

---

<a name="es"></a>
## Español

[English](#en) · **Español** · [Português](#pt) · [Français](#fr) · [Deutsch](#de) · [Italiano](#it)

wa2html convierte el export de un chat de WhatsApp en **un solo archivo HTML que se ve y funciona
como WhatsApp**: los audios se escuchan directo en el navegador, las fotos, stickers y videos
aparecen en la conversación, y se puede buscar, saltar a una fecha y cambiar el fondo y los
colores. No necesita apps, cuentas ni internet, así que la conversación se puede leer por muchos
años.

Nació para conservar los chats que importan, como la conversación con un ser querido que ya no
está.

- **No se pierde nada.** Cada línea de la transcripción queda en algún mensaje, cada archivo del
  export se incluye (o se copia) byte por byte, y la transcripción original va dentro de la página.
  Al terminar, wa2html vuelve a leer la página y lo comprueba todo con sumas SHA-256.
- **Nada sale de tu computador.** wa2html funciona sin conexión, y la página que crea está bloqueada
  para que no pueda cargar nada de internet.
- **En tu idioma.** El programa y la página están en español, inglés, portugués, francés, alemán e
  italiano.
- **Gratis y de código abierto** (licencia MIT).

> wa2html es un proyecto independiente, sin relación con WhatsApp ni Meta.

### Descarga

Baja el programa para tu computador desde el **[último release](https://github.com/EnriqueWood/wa2html/releases/latest)**:

| Computador | Archivo |
| --- | --- |
| Windows 10/11 (64 bits) | `wa2html-windows-x64.exe` |
| Windows, para terminal y scripts | `wa2html-cli-windows-x64.exe` |
| Mac con chip Apple (M1 o posterior) | `wa2html-macos-arm64` |
| Linux (64 bits) | `wa2html-linux-x64` |

Los Mac con Intel y otros sistemas pueden usar wa2html con Python (ver *Con Python* más abajo).

### Paso 1: exporta el chat desde WhatsApp

Estos pasos siguen la página de ayuda de WhatsApp
[Cómo exportar tu historial de chat](https://faq.whatsapp.com/1180414079177245/?locale=es_LA).

**Antes de empezar:** recorre el chat completo en el teléfono y toca cada foto, video o audio que
todavía muestre el botón de descarga. WhatsApp solo exporta los archivos que están guardados en el
teléfono; de los demás, la transcripción solo dice algo como `image omitted`.

**Android**

1. Abre el chat individual o en grupo.
2. Toca **⋮** (más opciones) > **Más** > **Exportar chat**.
3. Toca **Incluir archivos**.
4. Elige cómo enviarlo (por ejemplo Quick Share, Gmail o Chat) y lleva los archivos a tu
   computador. Según el teléfono recibirás un `.zip`, o un `.txt` más los archivos multimedia; en
   ese caso, ponlos todos en una misma carpeta.

**iPhone**

1. Abre el chat individual o en grupo.
2. Toca el nombre del contacto o grupo > **Exportar chat**.
3. Elige **Con todo el contenido multimedia**.
4. Elige cómo enviarlo (por ejemplo Guardar en Archivos) y copia el `.zip` a tu computador.

Según la ayuda de WhatsApp:

- En iPhone no se exportan los mensajes de visualización única.
- En Android, **Incluir archivos** adjunta el contenido multimedia *más reciente*. En un chat largo,
  revisa que el período que muestra wa2html empiece donde empieza el chat en el teléfono.
- Un export no se puede volver a importar en WhatsApp: es una copia para leer, no un respaldo.
  Conserva también tu respaldo de WhatsApp, y guarda el `.zip` original en más de un lugar seguro.

### Paso 2: conviértelo en una página

Abre wa2html. Una ventana muestra tres pasos:

1. **Chat exportado:** elige el `.zip` (o, en exports de Android sin zip, la carpeta con los
   archivos). wa2html muestra cuántos mensajes y archivos encontró.
2. **Opciones:** quién aparece a la derecha, fotos opcionales del contacto y tuya (cada una aparece
   en los audios de esa persona; la del contacto también en la cabecera; la tuya se recuerda), un
   archivo `.html` o una carpeta con los archivos (para chats muy grandes), y dónde guardarlo.
3. **Crear página:** wa2html guarda la página junto al `.zip` y la verifica. Cuando diga
   **Listo. Verificado: todos los mensajes y archivos están en la página**, haz clic en
   **Abrir página**.

El idioma de la ventana se cambia arriba a la derecha y wa2html lo recuerda.

**Windows:** haz doble clic en `wa2html-windows-x64.exe`, o arrastra el `.zip` sobre él para abrir
la ventana con el chat ya elegido. El programa no está firmado, así que Windows puede decir que
protegió tu PC: haz clic en **Más información** > **Ejecutar de todas formas**.

**Mac** (la primera vez, en Terminal, en la carpeta donde lo descargaste):

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # el programa no está firmado por Apple
./wa2html-macos-arm64                                # abre la ventana
```

Después también puedes abrirlo con doble clic en el Finder (se abre una Terminal junto a wa2html).

**Linux:** `chmod +x wa2html-linux-x64` y luego `./wa2html-linux-x64` abre la ventana.

**Con Python** (cualquier sistema con Python 3.10 o posterior):

```sh
pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip
wa2html-gui                            # la ventana
wa2html "WhatsApp Chat - Ana.zip"      # o la línea de comandos
```

Para guardar la página, cópiala junto con el `.zip` original.

### Línea de comandos

La misma conversión funciona sin ventana: `wa2html "WhatsApp Chat - Ana.zip"` (en Windows,
`wa2html-cli-windows-x64.exe "WhatsApp Chat - Ana.zip"`). La última línea del informe debe decir
`Verified ... identical to the export`; si dice `verification FAILED`, no confíes en esa página y
sigue usando el `.zip`. Opciones útiles: `--check` (solo el informe), `--mode folder` (carpeta en
vez de un archivo), `--me "Nombre"`, `--avatar foto.jpg` (contacto), `--my-avatar foto.jpg` (tú).
Nunca sobrescribe: si el archivo existe,
guarda como `... (2).html`. Todas las opciones: `--help` y la sección [English](#en).

### Qué muestra la página

Textos con formato y enlaces, audios con reproductor como el de WhatsApp (onda, avance, velocidad
1×/1,5×/2× y reproducción del siguiente audio), fotos a pantalla completa, videos, GIFs, stickers
(también animados), documentos, contactos, llamadas (las perdidas en rojo), ubicaciones, mensajes
eliminados y editados, avisos para los archivos que WhatsApp no incluyó y, al final, los archivos que
ningún mensaje menciona. El panel **Apariencia** cambia el tema, el fondo, los colores, el tamaño del
texto, el formato de hora, el idioma y quién aparece a la derecha. **Información del chat** muestra
estadísticas y permite descargar la transcripción original.

### Límites

Los exports de WhatsApp no traen respuestas (mensajes citados), reacciones, confirmaciones de
lectura ni fotos de perfil, así que la página no puede mostrarlos. Probado en Microsoft Edge; Chrome
y Firefox reproducen los audios de WhatsApp (Opus); Safari no está probado.

---

<a name="pt"></a>
## Português

[English](#en) · [Español](#es) · **Português** · [Français](#fr) · [Deutsch](#de) · [Italiano](#it)

O wa2html transforma a exportação de uma conversa do WhatsApp em **um único arquivo HTML com a
aparência e o funcionamento do WhatsApp**: os áudios tocam direto no navegador, fotos, figurinhas e
vídeos aparecem na conversa, e é possível pesquisar, ir para uma data e mudar o papel de parede e as
cores. Não precisa de aplicativo, conta nem internet, então a conversa continua legível por anos.

Foi criado para guardar as conversas que importam, como a conversa com alguém querido que já se foi.

- **Nada se perde.** Cada linha da transcrição é contabilizada, cada arquivo da exportação é incluído
  (ou copiado) byte a byte e a transcrição original vai dentro da página. Depois, o wa2html relê a
  página e confere tudo com somas SHA-256.
- **Nada sai do seu computador.** O wa2html funciona offline, e a página criada é bloqueada para não
  carregar nada da internet.
- **No seu idioma:** português, espanhol, inglês, francês, alemão e italiano.
- **Gratuito e de código aberto** (licença MIT).

> O wa2html é um projeto independente, sem vínculo com o WhatsApp ou a Meta.

### Download

Baixe o programa na **[versão mais recente](https://github.com/EnriqueWood/wa2html/releases/latest)**:
`wa2html-windows-x64.exe` (Windows 10/11, 64 bits), `wa2html-macos-arm64` (Mac com chip Apple, M1 ou
mais recente) ou `wa2html-linux-x64` (Linux, 64 bits). Para usar no terminal do Windows há também
`wa2html-cli-windows-x64.exe`. Macs com Intel e outros sistemas podem usar o wa2html com Python
(veja abaixo).

### Passo 1: exporte a conversa no WhatsApp

Passos da [página de ajuda do WhatsApp sobre exportar conversas](https://faq.whatsapp.com/1180414079177245/?locale=pt_BR).

**Antes de começar:** percorra toda a conversa no celular e toque em cada foto, vídeo ou áudio que
ainda mostre o botão de download. O WhatsApp só exporta as mídias guardadas no celular; para as
outras, a transcrição diz apenas algo como `image omitted`.

**Android**

1. Abra a conversa individual ou em grupo.
2. Toque em **⋮** (mais opções) > **Mais** > **Exportar conversa**.
3. Toque em **Incluir mídia**.
4. Escolha como enviar (por exemplo Quick Share, Gmail ou Conversa) e leve os arquivos para o
   computador. Dependendo do celular, você recebe um `.zip`, ou um `.txt` mais os arquivos de mídia;
   nesse caso, coloque todos na mesma pasta.

**iPhone**

1. Abra a conversa individual ou em grupo.
2. Toque no nome do contato ou do grupo > **Exportar conversa**.
3. Escolha **Com todas as mídias**.
4. Escolha como enviar (por exemplo Salvar em Arquivos) e copie o `.zip` para o computador.

Segundo a ajuda do WhatsApp: no iPhone, mensagens de visualização única não são exportadas; no
Android, **Incluir mídia** anexa as mídias *mais recentes* (numa conversa longa, confira se o período
mostrado pelo wa2html começa onde a conversa começa no celular); e a exportação não pode ser
importada de volta para o WhatsApp, pois não é um backup. Mantenha também o seu backup do WhatsApp e
guarde o `.zip` original em mais de um lugar seguro.

### Passo 2: transforme em uma página

Abra o wa2html. Uma janela mostra três passos: **1.** escolha o `.zip` (ou a pasta com os arquivos);
**2.** as opções (quem aparece à direita, uma foto para o cabeçalho, um arquivo `.html` ou uma pasta,
onde salvar); **3.** clique em **Criar página**. Quando aparecer **Pronto. Conferido: todas as
mensagens e arquivos estão na página**, clique em **Abrir página**. O idioma da janela pode ser
mudado no canto superior direito.

**Windows:** dê um duplo clique em `wa2html-windows-x64.exe` ou arraste o `.zip` sobre ele. O
programa não é assinado; se o Windows avisar que protegeu o computador, clique em
**Mais informações** > **Executar assim mesmo**.

**Mac** (na primeira vez, no Terminal, na pasta do download):

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # o programa não é assinado pela Apple
./wa2html-macos-arm64                                # abre a janela
```

**Linux:** `chmod +x wa2html-linux-x64` e depois `./wa2html-linux-x64`.

**Com Python** (3.10 ou mais recente):
`pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip` e depois
`wa2html-gui` (janela) ou `wa2html "WhatsApp Chat - Ana.zip"` (linha de comando).

### O que a página mostra

Textos com formatação e links, áudios com um player como o do WhatsApp (onda, avanço, velocidade
1×/1,5×/2×), fotos em tela cheia, vídeos, GIFs, figurinhas (inclusive animadas), documentos,
contatos, chamadas, localizações, mensagens apagadas e editadas, e avisos para as mídias que o
WhatsApp não incluiu. O painel de aparência muda tema, papel de parede, cores, tamanho do texto,
formato da hora e idioma. Todas as opções da linha de comando: `--help` e a seção [English](#en).

---

<a name="fr"></a>
## Français

[English](#en) · [Español](#es) · [Português](#pt) · **Français** · [Deutsch](#de) · [Italiano](#it)

wa2html transforme l'export d'une discussion WhatsApp en **un seul fichier HTML qui ressemble à
WhatsApp et fonctionne comme lui** : les messages vocaux se lisent directement dans le navigateur,
les photos, autocollants et vidéos apparaissent dans la conversation, et l'on peut chercher, aller à
une date et changer le fond d'écran et les couleurs. Pas besoin d'application, de compte ni
d'internet : la conversation reste lisible pendant des années.

Il a été écrit pour garder les discussions qui comptent, comme celle avec un proche disparu.

- **Rien ne se perd.** Chaque ligne de la transcription est prise en compte, chaque fichier de
  l'export est intégré (ou copié) à l'identique et la transcription d'origine est incluse dans la
  page. Ensuite, wa2html relit la page et vérifie tout avec des sommes SHA-256.
- **Rien ne quitte votre ordinateur.** wa2html fonctionne hors ligne et la page créée est verrouillée
  pour ne rien charger depuis internet.
- **Dans votre langue :** français, anglais, espagnol, portugais, allemand et italien.
- **Gratuit et open source** (licence MIT).

> wa2html est un projet indépendant, sans lien avec WhatsApp ni Meta.

### Téléchargement

Téléchargez le programme depuis la **[dernière version](https://github.com/EnriqueWood/wa2html/releases/latest)** :
`wa2html-windows-x64.exe` (Windows 10/11, 64 bits), `wa2html-macos-arm64` (Mac avec puce Apple, M1 ou
plus récent) ou `wa2html-linux-x64` (Linux, 64 bits). Pour le terminal Windows, il existe aussi
`wa2html-cli-windows-x64.exe`. Les Mac Intel et les autres systèmes peuvent utiliser wa2html avec
Python (voir plus bas).

### Étape 1 : exporter la discussion depuis WhatsApp

Étapes de la [page d'aide de WhatsApp sur l'export des discussions](https://faq.whatsapp.com/1180414079177245/?locale=fr_FR).

**Avant de commencer :** parcourez toute la discussion sur le téléphone et touchez chaque photo,
vidéo ou message vocal qui affiche encore le bouton de téléchargement. WhatsApp n'exporte que les
médias présents sur le téléphone ; pour les autres, la transcription indique seulement quelque chose
comme `image omitted`.

**Android**

1. Ouvrez la discussion individuelle ou de groupe.
2. Appuyez sur **⋮** (plus d'options) > **Plus** > **Exporter la discussion**.
3. Appuyez sur **Joindre médias**.
4. Choisissez comment l'envoyer (par exemple partage rapide, Gmail ou discussion) et transférez les
   fichiers sur l'ordinateur. Selon le téléphone, vous obtenez un `.zip`, ou un `.txt` et les
   fichiers médias ; dans ce cas, placez-les tous dans un même dossier.

**iPhone**

1. Ouvrez la discussion individuelle ou de groupe.
2. Appuyez sur le nom du contact ou du groupe > **Exporter la discussion**.
3. Choisissez **Avec tous les médias**.
4. Choisissez comment l'envoyer (par exemple Enregistrer dans Fichiers) et copiez le `.zip` sur
   l'ordinateur.

D'après l'aide de WhatsApp : sur iPhone, les messages à lecture unique ne sont pas exportés ; sur
Android, **Joindre médias** joint les médias *les plus récents* (pour une longue discussion, vérifiez
que la période affichée par wa2html commence là où la discussion commence sur le téléphone) ; et
l'export ne peut pas être réimporté dans WhatsApp, car ce n'est pas une sauvegarde. Gardez aussi
votre sauvegarde WhatsApp et conservez le `.zip` d'origine à plusieurs endroits sûrs.

### Étape 2 : en faire une page

Ouvrez wa2html. Une fenêtre présente trois étapes : **1.** choisissez le `.zip` (ou le dossier des
fichiers) ; **2.** les options (qui apparaît à droite, une photo pour l'en-tête, un fichier `.html` ou
un dossier, l'emplacement) ; **3.** cliquez sur **Créer la page**. Quand s'affiche **Terminé.
Vérifié : tous les messages et fichiers sont dans la page**, cliquez sur **Ouvrir la page**. La
langue de la fenêtre se change en haut à droite.

**Windows :** double-cliquez sur `wa2html-windows-x64.exe` ou faites glisser le `.zip` dessus. Le
programme n'est pas signé ; si Windows indique qu'il a protégé l'ordinateur, cliquez sur
**Informations complémentaires** > **Exécuter quand même**.

**Mac** (la première fois, dans le Terminal, dans le dossier du téléchargement) :

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # le programme n'est pas signé par Apple
./wa2html-macos-arm64                                # ouvre la fenêtre
```

**Linux :** `chmod +x wa2html-linux-x64`, puis `./wa2html-linux-x64`.

**Avec Python** (3.10 ou plus récent) :
`pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip`, puis
`wa2html-gui` (fenêtre) ou `wa2html "WhatsApp Chat - Anne.zip"` (ligne de commande).

### Ce que montre la page

Textes mis en forme et liens, messages vocaux avec un lecteur comme celui de WhatsApp (forme d'onde,
avance, vitesse 1×/1,5×/2×), photos en plein écran, vidéos, GIF, autocollants (animés aussi),
documents, contacts, appels, positions, messages supprimés et modifiés, et des avis pour les médias
que WhatsApp n'a pas inclus. Le panneau d'apparence change le thème, le fond d'écran, les couleurs,
la taille du texte, le format de l'heure et la langue. Toutes les options de la ligne de commande :
`--help` et la section [English](#en).

---

<a name="de"></a>
## Deutsch

[English](#en) · [Español](#es) · [Português](#pt) · [Français](#fr) · **Deutsch** · [Italiano](#it)

wa2html macht aus einem exportierten WhatsApp-Chat **eine einzige HTML-Datei, die wie WhatsApp
aussieht und funktioniert**: Sprachnachrichten laufen direkt im Browser, Fotos, Sticker und Videos
erscheinen im Verlauf, und man kann suchen, zu einem Datum springen sowie Hintergrund und Farben
ändern. Ohne App, ohne Konto und ohne Internet: So bleibt das Gespräch über Jahre lesbar.

Entstanden ist es, um wichtige Chats zu bewahren, etwa das Gespräch mit einem geliebten Menschen,
der nicht mehr da ist.

- **Nichts geht verloren.** Jede Zeile des Chatverlaufs wird erfasst, jede Datei des Exports wird
  bitgenau eingebettet (oder kopiert), und der ursprüngliche Verlauf steckt mit in der Seite.
  Anschließend liest wa2html die Seite erneut und prüft alles mit SHA-256-Prüfsummen.
- **Nichts verlässt deinen Computer.** wa2html arbeitet offline, und die erzeugte Seite ist so
  gesperrt, dass sie nichts aus dem Internet laden kann.
- **In deiner Sprache:** Deutsch, Englisch, Spanisch, Portugiesisch, Französisch und Italienisch.
- **Kostenlos und Open Source** (MIT-Lizenz).

> wa2html ist ein unabhängiges Projekt und steht in keiner Verbindung zu WhatsApp oder Meta.

### Download

Lade das Programm aus der **[neuesten Version](https://github.com/EnriqueWood/wa2html/releases/latest)** herunter:
`wa2html-windows-x64.exe` (Windows 10/11, 64 Bit), `wa2html-macos-arm64` (Mac mit Apple-Chip, M1 oder
neuer) oder `wa2html-linux-x64` (Linux, 64 Bit). Für das Windows-Terminal gibt es zusätzlich
`wa2html-cli-windows-x64.exe`. Macs mit Intel und andere Systeme können wa2html mit Python nutzen
(siehe unten).

### Schritt 1: Chat in WhatsApp exportieren

Schritte aus der [WhatsApp-Hilfeseite zum Exportieren von Chats](https://faq.whatsapp.com/1180414079177245/?locale=de_DE).

**Vorher:** Scrolle auf dem Handy durch den ganzen Chat und tippe auf jedes Foto, Video und jede
Sprachnachricht, die noch eine Download-Schaltfläche zeigen. WhatsApp exportiert nur Medien, die auf
dem Handy gespeichert sind; für die übrigen steht im Verlauf nur etwa `image omitted`.

**Android**

1. Öffne den Einzel- oder Gruppenchat.
2. Tippe auf **⋮** (weitere Optionen) > **Mehr** > **Chat exportieren**.
3. Tippe auf **Einschließlich Medien**.
4. Wähle, wie du ihn senden möchtest (z. B. Schnellteilen, Gmail oder Chat), und bringe die Dateien
   auf den Computer. Je nach Handy bekommst du eine `.zip`-Datei oder eine `.txt`-Datei plus
   Mediendateien; lege sie in diesem Fall alle in einen gemeinsamen Ordner.

**iPhone**

1. Öffne den Einzel- oder Gruppenchat.
2. Tippe auf den Namen des Kontakts oder der Gruppe > **Chat exportieren**.
3. Wähle **Mit allen Medien**.
4. Wähle, wie du ihn senden möchtest (z. B. In Dateien speichern), und kopiere die `.zip`-Datei auf
   den Computer.

Laut WhatsApp-Hilfe: Auf dem iPhone werden Nachrichten zur einmaligen Ansicht nicht exportiert; auf
Android hängt **Einschließlich Medien** die *neuesten* Medien an (prüfe bei einem langen Chat, ob der
von wa2html angezeigte Zeitraum dort beginnt, wo der Chat auf dem Handy beginnt); und ein Export kann
nicht wieder in WhatsApp importiert werden, da er kein Backup ist. Behalte also auch dein
WhatsApp-Backup und bewahre die ursprüngliche `.zip`-Datei an mehr als einem sicheren Ort auf.

### Schritt 2: daraus eine Seite machen

Öffne wa2html. Ein Fenster zeigt drei Schritte: **1.** die `.zip`-Datei (oder den Ordner mit den
Dateien) wählen; **2.** die Optionen (wer rechts erscheint, ein Foto für die Kopfzeile, eine
`.html`-Datei oder ein Ordner, Speicherort); **3.** auf **Seite erstellen** klicken. Sobald
**Fertig. Geprüft: Alle Nachrichten und Dateien sind in der Seite** erscheint, auf **Seite öffnen**
klicken. Die Sprache des Fensters lässt sich oben rechts ändern.

**Windows:** Doppelklicke auf `wa2html-windows-x64.exe` oder ziehe die `.zip`-Datei darauf. Das
Programm ist nicht signiert; meldet Windows, dass es den PC geschützt hat, klicke auf
**Weitere Informationen** > **Trotzdem ausführen**.

**Mac** (beim ersten Mal im Terminal, im Download-Ordner):

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # das Programm ist nicht von Apple signiert
./wa2html-macos-arm64                                # öffnet das Fenster
```

**Linux:** `chmod +x wa2html-linux-x64`, dann `./wa2html-linux-x64`.

**Mit Python** (3.10 oder neuer):
`pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip`, dann
`wa2html-gui` (Fenster) oder `wa2html "WhatsApp Chat - Anna.zip"` (Kommandozeile).

### Was die Seite zeigt

Formatierte Texte und Links, Sprachnachrichten mit einem Player wie bei WhatsApp (Wellenform,
Vorspulen, Geschwindigkeit 1×/1,5×/2×), Fotos im Vollbild, Videos, GIFs, Sticker (auch animierte),
Dokumente, Kontakte, Anrufe, Standorte, gelöschte und bearbeitete Nachrichten sowie Hinweise auf
Medien, die WhatsApp nicht exportiert hat. Im Darstellungs-Bereich lassen sich Design, Hintergrund,
Farben, Textgröße, Uhrzeitformat und Sprache ändern. Alle Optionen der Kommandozeile: `--help` und
der Abschnitt [English](#en).

---

<a name="it"></a>
## Italiano

[English](#en) · [Español](#es) · [Português](#pt) · [Français](#fr) · [Deutsch](#de) · **Italiano**

wa2html trasforma l'esportazione di una chat di WhatsApp in **un unico file HTML che ha l'aspetto e il
funzionamento di WhatsApp**: i messaggi vocali si ascoltano direttamente nel browser, foto, sticker e
video compaiono nella conversazione, e si può cercare, andare a una data e cambiare sfondo e colori.
Non servono app, account né internet, così la conversazione resta leggibile per anni.

È nato per conservare le chat che contano, come la conversazione con una persona cara che non c'è
più.

- **Non si perde nulla.** Ogni riga della cronologia viene conteggiata, ogni file dell'esportazione
  viene incluso (o copiato) identico byte per byte e la cronologia originale è inclusa nella pagina.
  Poi wa2html rilegge la pagina e verifica tutto con somme SHA-256.
- **Nulla esce dal tuo computer.** wa2html funziona offline e la pagina creata è bloccata in modo da
  non poter caricare nulla da internet.
- **Nella tua lingua:** italiano, inglese, spagnolo, portoghese, francese e tedesco.
- **Gratuito e open source** (licenza MIT).

> wa2html è un progetto indipendente, non affiliato a WhatsApp o Meta.

### Download

Scarica il programma dall'**[ultima versione](https://github.com/EnriqueWood/wa2html/releases/latest)**:
`wa2html-windows-x64.exe` (Windows 10/11, 64 bit), `wa2html-macos-arm64` (Mac con chip Apple, M1 o
successivo) oppure `wa2html-linux-x64` (Linux, 64 bit). Per il terminale di Windows c'è anche
`wa2html-cli-windows-x64.exe`. I Mac Intel e gli altri sistemi possono usare wa2html con Python
(vedi sotto).

### Passo 1: esporta la chat da WhatsApp

Passi della [pagina di assistenza di WhatsApp sull'esportazione delle chat](https://faq.whatsapp.com/1180414079177245/?locale=it_IT).

**Prima di iniziare:** scorri tutta la chat sul telefono e tocca ogni foto, video o messaggio vocale
che mostra ancora il pulsante di download. WhatsApp esporta solo i file multimediali salvati sul
telefono; per gli altri la cronologia riporta soltanto qualcosa come `image omitted`.

**Android**

1. Apri la chat singola o di gruppo.
2. Tocca **⋮** (altre opzioni) > **Altro** > **Esporta chat**.
3. Tocca **Includi file multimediali**.
4. Scegli come inviarla (ad esempio Condivisione rapida, Gmail o Chat) e porta i file sul computer.
   A seconda del telefono otterrai un file `.zip`, oppure un `.txt` più i file multimediali; in questo
   caso mettili tutti nella stessa cartella.

**iPhone**

1. Apri la chat singola o di gruppo.
2. Tocca il nome del contatto o del gruppo > **Esporta chat**.
3. Scegli **Con tutti i media**.
4. Scegli come inviarla (ad esempio Salva nei file) e copia il file `.zip` sul computer.

Secondo l'assistenza di WhatsApp: su iPhone i messaggi con l'opzione visualizza una volta non vengono
esportati; su Android **Includi file multimediali** allega i file *più recenti* (in una chat lunga,
controlla che il periodo mostrato da wa2html inizi dove inizia la chat sul telefono); e l'esportazione
non può essere reimportata in WhatsApp, perché non è un backup. Conserva anche il backup di WhatsApp e
tieni il file `.zip` originale in più di un posto sicuro.

### Passo 2: trasformala in una pagina

Apri wa2html. Una finestra mostra tre passi: **1.** scegli il file `.zip` (o la cartella con i file);
**2.** le opzioni (chi appare a destra, una foto per l'intestazione, un file `.html` o una cartella,
dove salvare); **3.** fai clic su **Crea pagina**. Quando compare **Fatto. Verificato: tutti i
messaggi e i file sono nella pagina**, fai clic su **Apri pagina**. La lingua della finestra si
cambia in alto a destra.

**Windows:** fai doppio clic su `wa2html-windows-x64.exe` oppure trascinaci sopra il file `.zip`. Il
programma non è firmato; se Windows avvisa di aver protetto il PC, fai clic su
**Ulteriori informazioni** > **Esegui comunque**.

**Mac** (la prima volta, nel Terminale, nella cartella del download):

```sh
chmod +x wa2html-macos-arm64
xattr -d com.apple.quarantine wa2html-macos-arm64   # il programma non è firmato da Apple
./wa2html-macos-arm64                                # apre la finestra
```

**Linux:** `chmod +x wa2html-linux-x64`, poi `./wa2html-linux-x64`.

**Con Python** (3.10 o successivo):
`pip install https://github.com/EnriqueWood/wa2html/archive/refs/heads/main.zip`, poi
`wa2html-gui` (finestra) oppure `wa2html "WhatsApp Chat - Anna.zip"` (riga di comando).

### Cosa mostra la pagina

Testi formattati e link, messaggi vocali con un lettore come quello di WhatsApp (forma d'onda,
avanzamento, velocità 1×/1,5×/2×), foto a schermo intero, video, GIF, sticker (anche animati),
documenti, contatti, chiamate, posizioni, messaggi eliminati e modificati, e avvisi per i file che
WhatsApp non ha incluso. Il pannello dell'aspetto cambia tema, sfondo, colori, dimensione del testo,
formato dell'ora e lingua. Tutte le opzioni della riga di comando: `--help` e la sezione
[English](#en).
