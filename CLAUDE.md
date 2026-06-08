# CLAUDE.md — Groove Candy Slide Maker

App qui transforme **1 lien YouTube → 3 slides vidéo (50s)** pour les carrousels Instagram de
Groove Candy. Pipeline : métadonnées YouTube (oEmbed) → audio (yt-dlp) → macaron vinyle
(Discogs) → 3 vidéos (ffmpeg).

## ⚠️ Architecture — deux systèmes coexistent

- **Système A — EN PRODUCTION** : Docker + Flask (`app.py`) + `groove_candy.py`, déployé sur
  **Railway**. Télécharge l'audio avec **yt-dlp**. Frontend `static/index.html`
  (endpoints `/search`, `/generate`, `/status`). **C'est ce qui tourne réellement.**
- **Système B — alternatif / chantier** : `api/*.js` (Vercel) + `cf-worker/` utilisant
  `youtubei.js`. Frontend `public/index.html`. **Pas utilisé en prod.** Ne pas confondre.

Prod : https://adventurous-insight-production-b84d.up.railway.app/

## Téléchargement audio — LE point sensible

**YouTube bloque/étrangle les IP de datacenter** (Railway). Un téléchargement yt-dlp **en
direct** depuis le serveur échoue avec `Read timed out`. La parade : un **proxy résidentiel
PacketStream**.

- `download_audio()` (dans `groove_candy.py`) : `--proxy $PROXY_URL`, réessaie jusqu'à 4× en
  **changeant d'IP** (`_rotate_proxy_url`) sur timeout/erreur réseau, avec
  `--force-ipv4 --socket-timeout 30 --retries 5 --fragment-retries 10`.
- **Variable Railway obligatoire** : `PROXY_URL=http://USER:CLE@proxy.packetstream.io:31112`.
  Sans elle → pas de proxy → échec (le message d'erreur le signale explicitement).
- **Cookies désactivés** quand le proxy est actif (ils déclenchent une détection de session sur
  proxy résidentiel). Forcer avec `YT_USE_COOKIES=1` si vraiment nécessaire.
- **SABR** (nouveau streaming YouTube qui peut casser les formats) : levier **sans
  redéploiement** → définir `YTDLP_PLAYER_CLIENT=android_vr,web_safari,tv` dans Railway.

## Déploiement

- Railway **redéploie automatiquement au merge sur `main`**.
- `entrypoint.sh` met yt-dlp à jour à chaque démarrage (`pip install -U yt-dlp`).
- CLI Railway locale non authentifiée (`railway login` requis pour lire les variables).

## Déboguer un échec de téléchargement (dans l'ordre)

1. Regarder ce qui est **réellement déployé** : `git show origin/main:groove_candy.py`
   (≠ code local éventuellement non committé).
2. Vérifier `PROXY_URL` dans Railway + que le **crédit PacketStream** n'est pas épuisé.
3. Lire les **logs Railway** — le message d'erreur de `download_audio` est explicite.
4. Si « format non disponible » / SABR → ajuster `YTDLP_PLAYER_CLIENT`.
5. Vérifier en prod : générer une slide → le job `/status` doit passer à `done`.

## Dépendances système (Docker)

ffmpeg · Deno (runtime JS requis par yt-dlp pour les challenges YouTube) · yt-dlp · Flask/gunicorn.
