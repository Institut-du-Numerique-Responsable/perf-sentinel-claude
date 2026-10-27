# Skill `perf-tests` : des tests d'intégration de performance pour Perf Sentinel

Date : 2026-10-27. Statut : validé par Robin le 2026-10-27.

## 1. Intention

Une équipe corrige les findings que Perf Sentinel remonte de la prod (N+1, requêtes en double, appels lents…). Pendant ce temps, chaque nouvelle feature ou chaque bugfix peut en ajouter de nouveaux. On vide la cale d'un côté pendant qu'elle se remplit de l'autre.

Le skill bouche cette entrée. Quand un dev a fini sa feature ou son bugfix, il lance le skill. Celui-ci écrit des tests d'intégration de performance sur le périmètre du changement. Ces tests tournent dans la CI de l'équipe avec OpenTelemetry activé, et Perf Sentinel analyse les traces produites. Un problème de perf se voit donc dans la PR, avant la prod.

Le skill est la **première pièce d'un plugin Claude**. Les deux suivantes ne sont pas couvertes ici :
- un MCP (ou harness) devant le Perf Sentinel Hub, pour lire les findings de prod et aider à les corriger ;
- l'intégration dans le workflow d'une équipe : tickets (Jira ou autre), priorités support et clients.

Ce document doit quand même laisser la place à ces deux pièces (voir §8).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Écrire, dans la stack du projet et dans son style de test, des tests d'intégration qui font passer le code modifié avec des données et des scénarios réalistes à l'échelle de la prod.
- Garantir que ces tests produisent des traces exploitables par Perf Sentinel, et brancher l'instrumentation et la CI quand elles manquent.
- Lancer les tests en local avec Perf Sentinel quand c'est possible, et montrer les findings au dev avant le push.
- Proposer des corrections ciblées pour les findings, sans régression technique ni fonctionnelle.

**Non-objectifs**
- Faire des tests de charge. Perf Sentinel juge une trace à la fois. Le skill traduit l'échelle de la prod en volume de données par requête, pas en nombre d'utilisateurs simultanés. Si le risque principal est la charge, il le dit et renvoie vers un outil de test de charge.
- Juger la performance lui-même. C'est le rôle de Perf Sentinel dans la CI.
- Décider du blocage de la PR. C'est un choix de l'équipe (voir §5.10).
- Migrer l'instrumentation d'un projet dans la PR de la feature (voir §5.5).

**Anti-objectifs : ce qui ferait échouer le skill même si les tests compilent**
- Des tests qui ne détectent rien parce qu'ils ne passent pas vraiment par le code modifié, ou parce que les données sont trop maigres pour qu'une boucle se voie.
- Des scénarios qui ne ressemblent à aucun usage réel. Ils ne trouveraient pas les problèmes qui sortiront en prod.
- Des tests désactivés en CI (par exemple avec une condition sur une variable d'environnement de la CI). Un test de perf qui ne tourne qu'en local ne protège rien.
- Un fix qui règle le finding mais casse un autre appelant, change le résultat métier ou ralentit un autre chemin.
- Un skill collé à une entreprise : chemins, flags, librairies internes ou conventions propres à une équipe.

## 3. Contraintes

- **Générique.** Le skill vise n'importe quelle équipe de n'importe quelle entreprise. Un service d'entreprise sert de cas d'essai, rien de ce service n'est écrit dans le skill.
- **Toutes les stacks que Perf Sentinel annonce** :
  - Java (Spring Boot, Quarkus, Micronaut) ;
  - C# (.NET, EF Core) ;
  - Python (Django, FastAPI) ;
  - Go (GORM) ;
  - Node.js (NestJS, Prisma) ;
  - Rust (Diesel, SeaORM) ;
  - Ruby (Rails) ;
  - PHP (Laravel, Symfony).

  Le skill s'adapte à ce qu'il trouve dans le dépôt.
- **Toutes les CI courantes** : GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI… Si la CI passe par une couche interne inconnue (shared library, template d'entreprise), le skill le dit et décrit le résultat à obtenir plutôt que d'inventer.
- **Sources de doc**, dans cet ordre :
  1. la doc officielle OpenTelemetry (opentelemetry.io) et celle du framework, car elles sont plus à jour ;
  2. la doc Perf Sentinel quand elle complète, toujours sur le site https://perf-sentinel.dev/docs/..., jamais sur le dépôt GitHub.
- **Ne pas figer les versions.** Les recommandations d'instrumentation bougent. Le skill donne la règle et le lien. Il demande de vérifier la version courante au moment d'écrire, au lieu de recopier des numéros de version.
- **Le starter ou la librairie d'abord, l'agent ensuite.** Quand une instrumentation sous forme de dépendance du projet existe, le skill la préfère à un agent zero-code, parce qu'elle donne plus de contrôle. Par exemple : `spring-boot-starter-opentelemetry` en Spring Boot 4, l'extension Quarkus, le SDK .NET configuré dans le code, les instrumentations Python ou Node déclarées dans le projet. L'agent sert quand il n'y a rien d'autre (Spring Boot 3, par exemple), ou quand le projet l'utilise déjà.
- **Rien ne démarre sans accord.** Le skill n'installe rien, ne modifie pas la CI et n'applique aucun fix sans l'accord du dev.

## 4. Lancement

- **Commande explicite** : `/perf-sentinel:perf-tests [précision]`. La précision est libre, par exemple `bugfix PROJ-1234` ou le nom de la feature. *Décidé par Robin.*
- **Suggestion par Claude** : quand le dev dit qu'il a fini ou demande une revue, et que le diff touche une base, un appel HTTP sortant ou une file de messages, Claude propose le skill en une ligne. Rien ne démarre sans un oui. *Décidé par Robin.*
- **Plus tard**, le workflow ticket du plugin pourra appeler le skill à la bonne étape (§8).

## 5. Déroulé

Les étapes sont dans l'ordre. Chaque étape qui touche au dépôt ou à la machine du dev demande son accord.

### 5.1 Reconnaissance du projet
Le skill repère, sans rien modifier :
- la stack, depuis les fichiers du dépôt (`pom.xml`, `build.gradle(.kts)`, `*.csproj`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `package.json`, `Cargo.toml`, `Gemfile`, `composer.json`) et la version du framework ;
- la CI : `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `.circleci/`…, et s'il y a déjà une étape Perf Sentinel (`perf-sentinel capture`, `analyze`) ;
- l'instrumentation OpenTelemetry en place, et si elle produit bien des spans SQL et HTTP sortants ;
- la config Perf Sentinel (`.perf-sentinel.toml`, fichier d'acquittements) ;
- le style des tests d'intégration existants : framework, nommage, base réelle ou embarquée (Testcontainers, docker compose…), fixtures, classes de base, comment ils sont lancés.

### 5.2 Périmètre du changement
- Le skill lit le diff par rapport à la branche de base.
- Pour chaque méthode modifiée, il remonte les appelants jusqu'aux **points d'entrée** : endpoint HTTP, listener de messages, job planifié, batch, commande CLI.
- Il ne garde que les chemins qui font des I/O que Perf Sentinel voit : SQL, HTTP sortant, RPC, publication de messages.
- Il liste ce qu'il ignore, comme le code sans I/O ou l'UI, et pourquoi.

### 5.3 Contexte métier : se renseigner, puis demander
C'est l'étape qui évite les anti-objectifs. Le skill se renseigne d'abord seul :
- le ticket, s'il y a accès (MCP ou fichier) ;
- le diff ;
- le modèle de données ;
- les fixtures ;
- les findings de prod sur ces endpoints, quand le MCP du Hub existera.

Il pose ensuite au dev quelques questions concrètes, seulement sur ce qu'il n'a pas trouvé seul.

**Pour une feature**, l'usage typique à l'échelle de la prod :
- Qui l'utilise, et à quelle fréquence ?
- Quel volume de données pour un client typique, et pour le plus gros ?
- Y a-t-il des pics : fin de mois, import de masse, batch de nuit ?
- Est-ce que ça grossit avec le temps, par exemple un historique qui s'allonge ?
- Quels filtres et quelles tailles de page sont vraiment utilisés ?

**Pour un bugfix**, ce qui s'est passé :
- le finding ou l'incident ;
- l'endpoint concerné ;
- les conditions de données qui l'ont déclenché.

### 5.4 Scénarios proposés, puis validés
- Le skill montre une courte liste avant d'écrire la moindre ligne. Exemple : « `GET /clients/{id}/contrats`, client avec 200 contrats de 15 lignes chacun ».
- Le dev valide ou corrige.
- Les minimums de Perf Sentinel ne sont qu'un plancher : 5 répétitions pour un N+1, 10 pour qu'il soit critique. Le volume vient des réponses du dev.

### 5.5 Instrumentation, si elle manque ou est incomplète
- Le skill applique la règle « starter ou librairie d'abord » (§3).
- Il ajoute ce qu'il faut pour que les tests produisent des spans utilisables :
  - le texte SQL (`db.query.text` ou `db.statement`) ;
  - l'URL complète des appels sortants ;
  - `service.name` ;
  - `http.route` sur les spans serveur, si possible.
- Il échantillonne à 100 % pendant les tests.
- Il renvoie vers la page officielle de la stack, et vers la section correspondante de https://perf-sentinel.dev/docs/INSTRUMENTATION quand elle apporte quelque chose.
- Il connaît les pièges propres aux tests et les vérifie, en contrôlant chacun dans la doc courante. Exemples relevés pendant la recherche :
  - un `@SpringBootTest` coupe l'export de traces quand le module de test du tracing est présent, sauf réglage explicite (§9) ;
  - Spring Boot n'instrumente pas JDBC sans librairie en plus ;
  - Micronaut a un exporter à `none` par défaut ;
  - Python casse l'instrumentation avec plusieurs workers ou un rechargeur ;
  - certaines bibliothèques Rust émettent des événements et pas des spans ;
  - une JVM forkée par Maven ne peut pas écrire ses traces sur stdout.
- Si le projet utilise un agent et qu'un starter existe, le skill garde l'agent pour cette PR. Il signale que le starter existe et propose la migration à part.

### 5.6 Écriture des tests
- Dans le style du projet : même framework, mêmes conventions de nommage, mêmes classes de base, même façon de monter la base.
- Une **vraie base** du même moteur qu'en prod, si le projet le permet. Un N+1 ou un plan de requête ne se voit pas pareil sur une base embarquée.
- Des données conformes aux scénarios validés.
- Le test appelle le point d'entrée comme un vrai client.
- **Le test vérifie aussi le résultat métier.** Ce n'est pas seulement un générateur de traces : il doit rester vrai après un fix.
- Les tests doivent tourner en CI. Aucune désactivation conditionnelle à la CI.
- **Durée en CI.** Le volume vient des réponses du dev, mais le skill garde le plus petit jeu de données qui reproduit la forme de la prod. Par exemple, 200 contrats suffisent si le plus gros client en a 200, pas besoin de 10 000 clients. Il réutilise les conteneurs et fixtures existants. Si un test dépasse une minute en local, il le signale et propose de réduire. *Mon choix.*

### 5.7 Lancement en local, quand c'est possible
- Le skill vérifie les prérequis : le binaire `perf-sentinel`, Docker si les tests en ont besoin, la commande de test.
- Si le binaire manque, il propose de l'installer depuis la release officielle, avec vérification de la somme de contrôle.
- Il lance seulement les nouveaux tests : `perf-sentinel capture --output <fichier hors du dossier de build> -- <commande de test filtrée>`, puis `perf-sentinel analyze` avec la config du projet s'il y en a une.
- **Il vérifie les traces.** Le fichier ne doit pas être vide. Il doit contenir des spans SQL ou HTTP. Il doit surtout contenir les requêtes ou appels qui correspondent au code du diff. Si la cible n'est pas touchée, le test est faux même sans finding : le skill le dit et corrige le test.
- Si le lancement local est impossible, le skill dit pourquoi en une phrase et passe à la suite. La CI fera le contrôle.

### 5.8 Cas du bugfix : avant et après
- Le skill lance le même test sur le code de la branche de base, dans un worktree à part.
- Le finding doit sortir avant et disparaître après. Sinon, soit le test ne reproduit pas le problème, soit le fix ne le corrige pas, et le skill dit lequel des deux il soupçonne.
- Pour que ce soit possible, le test passe par le point d'entrée public (l'endpoint, le listener) et pas par des classes internes que le fix a pu changer. Si le test ne compile pas ou ne tourne pas sur la base malgré tout (signature d'API changée, migration), cette étape est faite au mieux : le skill le dit, et elle ne bloque pas la suite. *Mon choix.*

### 5.9 Propositions de correction, s'il y a des findings
Le skill s'appuie sur le finding et sur la suggestion de Perf Sentinel, sans la croire sur parole : elle peut se tromper. Il propose **un fix ciblé à la fois** et vérifie qu'il ne casse rien :
- **Avant** :
  - il cherche tous les appelants du code qu'il modifie, pas seulement le point d'entrée testé ;
  - il vérifie les pièges classiques : doublons ou pagination cassée par une jointure de chargement, ordre des résultats changé par un chargement en lot, cache qui renvoie une donnée périmée, frontière de transaction ou chargement paresseux qui casse un autre appelant, données chargées pour rien sur un autre chemin.
- **Après** :
  - même résultat métier, moins d'appels ;
  - les tests existants qui couvrent le code touché passent, unitaires et d'intégration ;
  - un appelant non couvert par un test est signalé, pas supposé correct.
- Le dev décide de garder ou non chaque fix.

### 5.10 Branchement CI et blocage

**Le fonctionnement visé, avec uniquement ce qui existe dans Perf Sentinel** (*décidé par Robin*) :
1. **À chaque passage en CI, sur toutes les branches** : `capture` autour de l'étape de test, puis `analyze`, qui produit SARIF, JSON et HTML. Ces fichiers sont archivés avec le build. C'est la photo des findings du passage, sur le périmètre que les tests parcourent.
2. **Le fichier d'acquittements sert de registre des findings non résolus.** C'est `.perf-sentinel-acknowledgments.toml`, versionné dans le dépôt, donc partagé par toutes les branches et fusionné comme du code.
   - Il liste les findings connus que l'équipe a choisi de ne pas corriger tout de suite, chacun avec une raison, un relecteur et une expiration.
   - Quand un finding est corrigé, son entrée ne correspond plus à rien. Perf Sentinel la signale en `unmatched_acknowledgment`, et l'équipe la supprime.
   - Une entrée expirée cesse de compter, et son finding repasse dans le gate (https://perf-sentinel.dev/docs/ACKNOWLEDGMENTS).
3. **Le gate, au choix de l'équipe** : `analyze --ci` bloque tout finding non acquitté. Le dev corrige, ou acquitte dans sa PR, et ce choix passe en revue.

Le Hub ne change pas : la CI peut le lire (`GET /api/findings`), mais ne l'alimente pas (`PerfSentinelHub/docs/DEPLOYMENT.md`, « The CI reads, it does not feed »).

**Ce que fait le skill** :
- Si la CI n'exécute pas Perf Sentinel, le skill propose de l'ajouter.
- Quand un de ses tests sort un finding que le dev choisit de ne pas corriger, il propose l'entrée d'acquittement prête à coller : signature, raison, relecteur à remplir, et **toujours une date d'expiration**, car une entrée sans date est permanente. Le dev la garde ou non. *L'expiration systématique est mon choix.*
- Il signale les entrées `unmatched_acknowledgment` que le passage local fait apparaître, car elles peuvent être supprimées. Le principe : entourer l'étape de test existante avec `perf-sentinel capture`, sans ajouter une étape à côté qui relancerait toute la suite. Ensuite, lancer `perf-sentinel analyze`.
- Il s'appuie sur https://perf-sentinel.dev/docs/CI et sur le modèle qui correspond à la CI détectée.
- **Affichage dans la PR.** Le skill reprend ce que le modèle Perf Sentinel de la CI détectée sait déjà faire (SARIF vers le code scanning, commentaire de PR, rapport GitLab). Il ne crée pas d'intégration nouvelle. Si cela demande un jeton ou une permission, il le dit. *Mon choix.*
- **Blocage** : le skill recommande de bloquer sur un finding, de préférence seulement sur les PR, pas sur la branche principale. Le gate juge toutes les traces de la suite, sans comparaison à la branche de base. Un IT ne couvre qu'un bout de code précis, donc la dette du reste de la codebase n'y apparaît pas. Si des IT existants révèlent des problèmes que l'équipe choisit de ne pas corriger, c'est à elle de les acquitter. Le skill ne gère pas cette dette à sa place. *Décidé par Robin.* Il montre ce qui change dans la CI détectée, en général `analyze --ci` dont le code de sortie fait échouer le job. Il ne l'active pas lui-même : c'est un choix de l'équipe. *Décidé par Robin.*
- **Seuils** : le skill rappelle les seuils réellement appliqués, tirés du `.perf-sentinel.toml` ou, à défaut, des valeurs par défaut de Perf Sentinel. Il indique lesquels de ses tests les dépasseraient si le code avait un défaut. Il suggère aussi un seuil sur la part de spans utilisables, pour qu'une instrumentation cassée fasse échouer la CI au lieu de passer au vert. *Le rappel des seuils est décidé par Robin, la suggestion est mon choix.*

### 5.11 Résumé final
Un résumé court pour le dev :
- les scénarios testés ;
- les fichiers créés ou modifiés ;
- le résultat local (findings, ou la raison de l'absence de lancement) ;
- les fixes proposés et leur statut ;
- ce que la CI fera ;
- ce que le skill n'a pas couvert, et pourquoi.

## 6. Emballage

- **Dépôt** : d'abord sur le compte GitHub personnel de Robin (`robintra`), migré plus tard vers l'organisation Institut-du-Numerique-Responsable quand il sera mûr. *Décidé par Robin.* Le nom du dépôt, `perf-sentinel-claude-plugin`, est *mon choix*.
- **Plugin** : nom `perf-sentinel`, donc commandes `/perf-sentinel:...`. Le marketplace est dans le même dépôt (`.claude-plugin/marketplace.json` avec `"source": "./"`), pour que l'installation se fasse en une commande. *Mon choix.*
- **Structure**, à préciser par le builder :
  ```
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
  skills/perf-tests/SKILL.md          moins de 500 lignes, le déroulé du §5
  skills/perf-tests/references/       une fiche par stack, une par CI, les détecteurs
  skills/perf-tests/scripts/          seulement si un script évite une erreur réelle
  README.md, LICENSE, CHANGELOG.md
  ```
  Le `.mcp.json` arrivera avec la pièce 2.
- **Frontmatter portable** : seulement les champs acceptés hors de Claude Code (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`). Le skill reste ainsi utilisable sur claude.ai. Son vrai usage reste quand même Claude Code, puisqu'il touche au dépôt et lance des tests. *Mon choix.*
- **Langue** : le skill et ses fiches sont en anglais, pour toucher n'importe quelle équipe. Il répond dans la langue du dev. *Mon choix.*
- **Fiches par stack** : chaque fiche donne la règle, les pièges et les liens officiels. Elle ne donne pas de numéros de version figés (§3). La fiche Perf Sentinel résume ce que chaque détecteur attend pour sortir, avec les valeurs par défaut et le lien vers le site.
- **Couverture de la v1** : toutes les stacks et les CI du §3 ont leur fiche dès la v1, comme Robin l'a demandé. Chaque fiche dit si elle a été essayée de bout en bout (§7) ou seulement écrite d'après la doc officielle. Pour une fiche non essayée, le skill est plus prudent : il vérifie la doc courante avant d'agir, et il insiste sur le contrôle des traces (§5.7). *Le marquage est mon choix.*

## 7. Validation

Le skill est prêt quand il a été essayé sur :
- **un service Spring Boot 4 d'entreprise** (starter, Testcontainers, Jenkins), avec une feature et un bugfix de perf ;
- **des services non JVM de `perf-sentinel-simulation-lab`**, qui contient un service par stack : `dotnet-svc` (avec un projet de tests `dotnet-svc.tests`), `fastapi-svc`, `django-svc`, `go-svc`, `nest-svc`, `diesel-svc`, `seaorm-svc`, `rails-svc`, `laravel-svc`, `symfony-svc`, `quarkus-svc`… Pour la v1 : au moins `dotnet-svc` et `fastapi-svc`. Les autres stacks peuvent être essayées ensuite au même endroit, et leur fiche passe alors à « essayée ». *Mon choix : Robin n'a pas d'autre projet non JVM sous la main.*

Pour chaque essai :
- les tests écrits doivent faire sortir un finding sur un N+1 volontaire ;
- ils ne doivent rien sortir une fois le N+1 corrigé ;
- ils doivent toucher le code du diff.

Le déclenchement du skill (la description) se mesure avec `claude plugin eval`.

## 8. Place laissée aux pièces suivantes

- **MCP du Hub**. À l'étape 5.3, le skill pourra lire les findings de prod sur les endpoints concernés. À l'étape 5.9, il pourra s'appuyer sur l'historique des findings. Le skill doit marcher sans ce MCP et en profiter s'il est là.
- **Workflow ticket**. Le skill accepte une référence de ticket en argument. Un futur workflow pourra l'appeler avec cette référence.
- **Corriger les findings de prod.** Robin le fait déjà en demandant des propositions de fix à l'IA. Ce besoin relève de la pièce 2 : le §5.9 donne les règles de non-régression qu'elle pourra reprendre.

## 9. Ce qui reste ouvert

**Laissé au builder**
- Le découpage exact de `SKILL.md` et des fiches.
- Le format du résumé final.
- La manière de remonter les appelants selon la stack (recherche texte, LSP s'il est là…).

**Vérifié pendant la relecture** (à reprendre dans les fiches)
- **Spring Boot 4.x** : `@SpringBootTest` coupe l'export de traces seulement si `spring-boot-micrometer-tracing-test` est sur le classpath de test. Il le fait en posant `management.tracing.export.enabled=false`. Une clé par exporter, `management.tracing.export.otlp.enabled=true`, prend le dessus. Pour exporter depuis les tests, deux options : poser cette clé avec `management.opentelemetry.tracing.export.otlp.endpoint`, ou utiliser `@AutoConfigureTracing` (ou `spring.test.tracing.export=true`). Le service Spring Boot 4 du §7 exporte donc très probablement bien ses traces. Lu dans les sources de la 4.1.1, pas observé en lançant un test.
- **.NET** : `SetDbStatementForText` a été supprimé de SqlClient (1.12.0-beta.3) et d'EF Core (1.13.0-beta.1). Le texte SQL, nettoyé, est maintenant toujours émis :
  - en `db.query.text` pour SqlClient ;
  - en `db.statement` par défaut pour EF Core, ou en `db.query.text` avec `OTEL_SEMCONV_STABILITY_OPT_IN=database`.

  La doc Perf Sentinel est fausse sur ce point (`INSTRUMENTATION.md:952-955`). Non vérifié : les littéraux sont maintenant remplacés par `?`, et il reste à voir si la détection N+1 le gère bien en .NET.
- **Python** : les deux exemples de la doc Perf Sentinel (`INSTRUMENTATION.md:1034-1038` et `:1076-1080`) n'appellent jamais `trace.set_tracer_provider(provider)`. Les spans ne partent donc nulle part. Pour SQLAlchemy en async, il faut aussi passer `engine.sync_engine`, et appeler `AsyncPGInstrumentor` alors qu'il n'est pas appelé.

**Corrigé dans Perf Sentinel**
- Les deux erreurs de doc .NET et Python ci-dessus ont été corrigées dans la branche `main` de perf-sentinel (commit `fa0b45ab`). Les fiches du skill doivent suivre la version corrigée.
