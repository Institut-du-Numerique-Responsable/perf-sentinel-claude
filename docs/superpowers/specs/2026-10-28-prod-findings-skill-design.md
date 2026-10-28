# Skill `prod-findings` : classer et corriger les findings de prod lus dans le Hub

Date : 2026-10-28. Statut : validé par Robin le 2026-10-28. Le plan attend le contrat des champs de volume (§3).

## 1. Intention

C'est la **pièce 2** du plugin Claude, après `perf-tests` (pièce 1, `docs/superpowers/specs/2026-10-27-perf-tests-skill-design.md`). La pièce 1 empêche les nouveaux findings d'entrer. Celle-ci vide la cale : elle lit les findings que Perf Sentinel a remontés de la prod, les classe par poids sur le gaspillage, puis aide à les corriger.

Aujourd'hui, Robin le fait à la main. Il laisse l'IA prendre le contrôle de Chrome, connecté avec son SSO. L'IA lit le dashboard Grafana (branché directement sur le démon de prod) et le Hub de prod. Elle classe les findings par impact décroissant, puis propose des correctifs à partir de l'emplacement de code que porte chaque finding. Le détour par le navigateur est lent et fragile : l'IA lit des écrans au lieu de lire des données.

Le skill remplace ce détour par la CLI de Perf Sentinel, qui sait déjà se connecter au Hub et le lire. **Pas de MCP, pas de serveur à ajouter.** *Mon choix*, après lecture du Hub et de la CLI : tout ce qu'il faut existe déjà (§3), sauf un volume fiable, qui fait l'objet d'un chantier séparé (§3, prérequis).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Lire les findings de prod d'un ou plusieurs services dans le Hub, sans navigateur, avec l'identité de la personne qui lance le skill.
- Les classer pour que les premiers corrigés soient ceux qui font le plus fondre le gaspillage (§5.3).
- Expliquer chaque finding en langage simple, avec son volume chiffré, sa période et sa source.
- Au choix de l'utilisateur, s'arrêter au classement (pour répartir le travail entre équipes) ou aller jusqu'au correctif dans le dépôt courant. *Décidé par Robin*, qui préfère qu'on aille jusqu'au correctif quand c'est possible.
- Regrouper les correctifs en lots homogènes, de la taille d'une relecture rapide (§5.5).
- Prouver chaque correctif en CI avec un test de non-régression écrit par `perf-tests` (§5.7).
- Proposer d'acquitter un finding qui s'avère être un faux positif (§5.8). *Demandé par Robin.*

**Non-objectifs**
- Suivre l'effet en prod après le déploiement. *Décidé par Robin* : en entreprise, personne ne relance un outil pour un bilan hypothétique. L'équipe regarde le Hub ou Grafana, et le ratio de gaspillage qui fond. Le skill facilite ce regard en mettant les signatures dans la PR (§5.9).
- Lire le démon directement. *Décidé par Robin* : en entreprise, tout passe par le Hub.
- Ouvrir des tickets ou suivre les priorités support : c'est la pièce 3.
- Refaire le travail de `perf-tests` : le skill lui passe la main pour les tests.

**Anti-objectifs**, ce qui ferait échouer le skill même s'il « marche » (*proposés par moi, validés par Robin*) :
- Un correctif qui change le comportement : cache qui sert une donnée périmée, jointure qui change l'ordre ou les doublons d'un résultat, frontière de transaction déplacée.
- Des chiffres présentés comme plus sûrs qu'ils ne sont : un volume ou une économie cités sans leur période ni leur source, ou une borne basse présentée comme un volume.
- Corriger un finding que l'équipe a acquitté comme voulu.
- Une PR fourre-tout, qui mélange les types de correctifs ou dépasse une relecture rapide.
- Toucher le code d'une autre équipe sans que l'utilisateur l'ait demandé.

## 3. Contraintes

**Ce qui existe déjà**, à réutiliser tel quel :
- `perf-sentinel login --hub <url>` connecte le terminal par un *device flow* : la CLI affiche un code, la personne l'approuve dans son navigateur connecté au Hub (SSO), la CLI garde un jeton personnel (`pshub_…`). Ce jeton agit au nom de la personne et avec ses droits, jamais admin, 8 heures au plus (`PerfSentinelHub/docs/ACCESS-CONTROL.md`, « Terminal tokens »). Le Hub doit avoir la connexion terminal activée (`Hub:Auth:TrustedProxyNetworks`).
- `perf-sentinel hub findings --environment <env> --status active --format json` relaie la réponse de `GET /api/findings` du Hub sans la modifier. Filtres : `--service`, `--finding-type`, `--severity`, `--status`, `--source-id`, `--limit` (50 par défaut).
- Chaque finding porte son endpoint, son type, sa sévérité, sa signature, son emplacement de code (fonction, fichier, ligne) quand les spans le donnent, la suggestion de Perf Sentinel, et `green_impact.estimated_extra_io_ops`, les I/O en trop **pour une trace**. Le Hub y ajoute `first_seen`, `last_seen`, `status`, `sources` et `acks` (`PerfSentinelHub/docs/API.md`).
- `perf-sentinel hub incidents` liste les incidents, dont les findings figés sont comptés sur la fenêtre de l'incident.
- `perf-sentinel hub ack --source-id <id> --signature <sig> --reason "…" [--expires 30d]` acquitte un finding au démon derrière une source, au nom de la personne.
- `references/fix-safety.md` du skill `perf-tests` donne les règles de non-régression (avant, accord, après, décision).

**Ce qui manque : un volume fiable (prérequis).** Le `seen_count` de `/api/findings` est le nombre de détections présentes dans l'anneau du démon au dernier poll, ou 1 après un push, selon qui a écrit en dernier. Ce n'est pas un volume : il baisse quand l'anneau tourne, retombe à zéro au redémarrage, et le Hub ne garde que la présence par jour (`finding_observations`), sans compte. Robin a décidé de combler ce manque à la source : **un compteur cumulatif par signature dans le démon, exposé par `/api/findings`, que le Hub enregistre par jour.** Ce chantier est confié à la session qui prépare les releases du Hub. Il a sa propre conception, validée par Robin avant tout code. Ce que le skill en attend :
- pour chaque finding, un nombre de détections sur une fenêtre (par jour, ou sur `from`/`to`) ;
- un vrai volume, qui survit à l'éviction de l'anneau et au redémarrage du démon, et que le push ne fausse pas ;
- un inconnu distinct de zéro : un jour sans compte (avant la mise à jour, démon trop ancien) reste `null` ;
- un compte par source, que le skill additionne sur les sources de prod du périmètre. Un finding vu par plusieurs démons est classé sur la somme. *Mon choix* : c'est le gaspillage total qui compte ;
- l'échantillonnage du démon pris en compte. Le démon garde ou écarte des traces entières selon un taux (`daemon/sampling.rs`). Le compte doit soit être corrigé de ce taux, soit l'accompagner, pour que le skill extrapole et le dise. Sans l'un ou l'autre, c'est une borne basse, et le skill doit l'afficher comme telle.

Les noms et la forme exacte des champs viendront de cette conception. **Le plan d'implémentation attend ce contrat** : ce document sera mis à jour quand il sera fixé, puis planifié.

**Ce qui manque aussi dans la CLI.** `perf-sentinel hub findings` ne transmet pas encore `from`, `to`, `offset`, `include_acked` et `signature`, que le Hub accepte. Sans eux, pas de période, pas d'exclusion des acquittés côté Hub, et pas de pagination : les lignes arrivent triées par `last_seen` et coupées à `--limit`, ce qui fausserait le classement sans le dire. Ces options sont ajoutées à la CLI dans la même release du moteur que le compteur de volume, pour qu'une seule version minimale suffise au skill. *Décidé par Robin.* En attendant, et pour un moteur trop ancien, le skill lit toutes les lignes (`--limit` jusqu'à `Hub:MaxReadLimit`), filtre lui-même, et dit si la liste a pu être tronquée. Le skill vérifie la version de la CLI et dit ce qui lui manque.

**Autres contraintes**
- Les conventions de la pièce 1 s'appliquent : frontmatter portable, skill et fiches en anglais, réponse dans la langue de l'utilisateur, accord avant chaque écriture, pas de version figée dans les fiches, doc Perf Sentinel citée sur https://perf-sentinel.dev/docs/ et jamais sur le dépôt.
- Aucun accès réseau implicite : le skill n'appelle que le Hub que l'utilisateur a choisi avec `perf-sentinel login` ou `--hub`.
- Le jeton ne passe jamais dans la conversation. Le skill s'appuie sur le jeton que garde la CLI, ou sur `PERF_SENTINEL_HUB_TOKEN` déjà présent dans l'environnement, sans l'afficher.

## 4. Lancement

- Commande : `/perf-sentinel:prod-findings [précision]`. *Mon choix pour le nom.* La précision libre restreint le périmètre : un service, un type de finding, un environnement, ou « classement seul ».
- Le skill ne démarre que sur la commande, ou sur un oui à une proposition. Il ne se propose pas de lui-même après une feature : c'est le rôle de `perf-tests`. *Mon choix* : un dev qui vient de finir une feature n'est pas en train de vider la cale.

## 5. Déroulé

### 5.1 Connexion
- Le skill vérifie que la CLI est installée et qu'elle peut lire le Hub (un premier `perf-sentinel hub findings --limit 1 --format json`).
- Sans jeton valide (`401`), il explique `perf-sentinel login --hub <url>` en une étape et attend que la personne l'ait fait. Il ne lance pas la commande lui-même, car elle attend une approbation dans le navigateur.
- Sur un `403`, il dit que le compte n'a pas accès à ce projet dans le Hub, et à qui le demander (l'admin du Hub), sans insister.
- Il n'enregistre aucun jeton et n'en affiche aucun.

### 5.2 Périmètre
- **Environnement** : la production par défaut. Un autre environnement si la précision le demande. *Mon choix.*
- **Services** : par défaut, ceux du dépôt courant, reconnus comme dans la reconnaissance de `perf-tests` (nom du service OpenTelemetry dans la config, le code ou les manifestes). Si le dépôt n'en révèle aucun, ou si l'utilisateur veut un classement sur plusieurs services, le skill demande lesquels.
- **Statut** : `active` seulement.
- **Acquittés** : exclus par défaut, avec leur nombre affiché pour qu'on sache qu'ils existent. Un finding est exclu quand toutes les sources du périmètre qui le portent l'ont acquitté, comme le fait `include_acked=false` du Hub.

### 5.3 Classement
Trois groupes, dans cet ordre (*décidé par Robin*) :
1. **N+1 et redondants**, par I/O évitables décroissantes sur la période : détections × `estimated_extra_io_ops`. Ce sont les seuls types que le moteur compte comme I/O évitables (`is_avoidable_io`), donc ceux qui pèsent sur le ratio de gaspillage.
2. **Lents** : gains rapides comme le groupe 1, mais hors du ratio de gaspillage. Ils comptent pourtant : une requête lente peut tenir des verrous en base et provoquer des crashs (*remarque de Robin*). Ils sont donc classés par risque : la sévérité d'abord, puis le nombre de détections. Une écriture lente, ou une requête lente dans une transaction qui écrit, est signalée comme risque de verrou et remonte en tête du groupe. *Mon choix, tiré de cette remarque.*
3. **Structurels** (fanout, chatty, pool saturation, serialized) : plus longs et plus risqués à traiter, sans impact chiffré. Classés par sévérité.

La période par défaut est les 7 derniers jours. *Mon choix.* Si le volume est inconnu pour un finding (prérequis pas encore déployé, démon trop ancien), le skill le classe dans son groupe par impact par trace et écrit en clair « volume inconnu ». Il n'invente jamais de volume.

### 5.4 Présentation
Pour chaque finding classé, une ligne simple, pensée pour un dev, un architecte ou un SRE qui sait à quoi sert Perf Sentinel sans en connaître les détails :
- ce qui se passe, en une phrase (« la requête des lignes part une fois par contrat ») ;
- le volume, sa période et sa source dans le Hub (« 48 200 I/O évitables sur 7 jours, source `prod-eu` ») ;
- l'endroit du code, et s'il est dans le dépôt courant ;
- pour un lent, s'il présente un risque de verrou en base ;
- le lien vers le finding dans le Hub, quand l'URL du Hub le permet.

En mode « classement seul », le skill s'arrête ici. Il propose la liste dans un format facile à transmettre aux équipes (un tableau Markdown, par service). *Mon choix pour le format.*

### 5.5 Lots
Le skill propose des lots homogènes, que l'utilisateur valide avant toute modification (*décidé par Robin*) :
- **redondants** : beaucoup par PR, car ajouter un cache ne fait presque courir aucun risque de régression et se relit vite ;
- **N+1** : plusieurs par PR tant qu'elle reste de la taille d'une relecture rapide ;
- **lents** : peu par PR, ils sont plus lourds et plus risqués ;
- jamais deux types dans le même lot ;
- seulement le code du dépôt courant. Un finding dont le code est ailleurs reste dans le classement, marqué « hors dépôt ».

### 5.6 Correctifs
- Le skill part du finding, de son emplacement de code et de la suggestion de Perf Sentinel, sans la croire sur parole.
- Il charge `fix-safety.md` et en applique les listes à chaque correctif.
- Il montre chaque correctif et attend un oui avant de l'appliquer, sur une branche par lot. *Mon choix pour la branche par lot.*
- Un correctif de lent ne doit pas créer le verrou qu'il veut éviter. Un index se crée sans bloquer la table quand la base le permet (`CREATE INDEX CONCURRENTLY` sur PostgreSQL, par exemple), et une migration lourde est signalée à l'utilisateur plutôt que glissée dans le lot.

### 5.7 Preuve en CI
Après les correctifs d'un lot, le skill passe la main à `perf-tests`, dans son mode bugfix avant/après : le test doit faire sortir le finding sur le code d'avant et ne plus le faire sortir après. Il ne réécrit pas ce que fait `perf-tests`.

*Mon choix pour le passage de main* : `prod-findings` propose `/perf-sentinel:perf-tests bugfix <signatures et endpoints>`, et `perf-tests` apprend à reconnaître dans `$ARGUMENTS` des signatures de findings. Il lit alors ces findings dans le Hub et saute les questions de bugfix dont il a la réponse (le finding, l'endpoint, les conditions). C'est un petit changement de `perf-tests`, livré avec celui du §8, avec ses évals rejouées.

### 5.8 Faux positif
Quand l'analyse du code montre qu'un finding est voulu ou sans effet réel, le skill ne corrige rien. Il explique pourquoi, puis propose :
- la commande `perf-sentinel hub ack`, avec une raison rédigée et une expiration. Il ne l'exécute qu'après un oui explicite, car elle change l'état de la prod. `hub ack` vise une seule source : quand plusieurs sources de prod portent le finding, le skill liste ces sources dans sa demande, et le oui couvre exactement cette liste, une commande par source. *Mon choix* : sinon le finding resterait affiché par les autres sources ;
- si le dépôt a un `.perf-sentinel-acknowledgments.toml`, l'entrée correspondante, prête à coller, avec une date d'expiration, comme le fait `perf-tests`. *Mon choix*, pour que la porte de CI reste cohérente avec la prod.

### 5.9 Pull request
Le skill rédige la description de chaque PR : le type de correctif, les findings corrigés avec leur signature, leur volume, sa période et sa source dans le Hub, et le test de non-régression ajouté. Les signatures permettent à l'équipe de retrouver les findings dans le Hub ou Grafana après le déploiement. Il ne commite, ne pousse et n'ouvre la PR que sur demande. *Mon choix.*

### 5.10 Résumé final
Ce qui a été classé, corrigé, acquitté, laissé de côté et pourquoi, et ce qui reste à faire par l'utilisateur.

## 6. Emballage

- Dans le même plugin, `perf-sentinel`, à côté de `perf-tests` : `skills/prod-findings/SKILL.md` et ses fiches. *Mon choix.*
- Une fiche des commandes `perf-sentinel hub` et des champs lus, sur le modèle de `references/perf-sentinel.md`. Les règles communes (`fix-safety.md`) ne sont pas copiées : le builder choisit de les déplacer dans un endroit partagé ou de les référencer.
- `allowed-tools` limité à la lecture (`perf-sentinel hub findings *`, `perf-sentinel hub incidents *`, `perf-sentinel --version`, `git diff`, `git log`). L'acquittement et les écritures restent soumis à accord.

## 7. Validation

- Évals de déclenchement avec `claude plugin eval`, comme pour `perf-tests` : démarre sur la commande, ne démarre pas tout seul, ne se propose pas après une feature, mode « classement seul » respecté.
- Essai de bout en bout dans `perf-sentinel-simulation-lab`, avec un Hub dont la connexion terminal est active et le prérequis de volume déployé : un N+1 et un redondant volontaires doivent sortir en tête du classement, être corrigés dans des lots séparés, et leur test `perf-tests` doit les faire sortir avant et pas après.
- Un cas sans volume (Hub ou démon d'avant le prérequis) : le skill doit écrire « volume inconnu » et ne rien inventer.
- Le banc demande un Hub de labo avec le contrôle d'accès et la connexion terminal actifs, une source dont le relais d'acquittement marche, et un rôle qui permet d'acquitter. Préparer ce scénario de labo fait partie du plan, sauf si le chantier du prérequis en fournit déjà un. *Mon choix.*
- `claude plugin eval` ne peut pas passer le *device flow* : les évals ne couvrent que le déclenchement et le comportement sans Hub joignable.

## 8. Lien avec les autres pièces

- **`perf-tests`** : son étape « Fixes » parle d'un outil MCP du Hub pour lire l'historique d'un finding. Ce sera plutôt `perf-sentinel hub findings` quand la personne est connectée. Mise à jour à faire dans `perf-tests` en même temps, ou juste après.
- **Pièce 3 (tickets)** : le classement seul pourra alimenter des tickets par équipe.

## 9. Ce qui reste ouvert

**En attente**
- Les noms et la forme des champs de volume, fixés par la conception du prérequis côté moteur et Hub.

**Laissé au builder**
- Le découpage de `SKILL.md` et des fiches.
- La façon de reconnaître le service OpenTelemetry d'un dépôt, en réutilisant ce que fait `perf-tests`.
- Le format exact du tableau de classement et de la description de PR.
