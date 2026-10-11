# 2026-10-11 Actions storage 100%
- Причина не установлена точно (API артефактов/кэшей закрыт прокси). Артефакты Pages ~1.3 МБ.
- deploy.yml: retention-days: 1 у Pages-артефакта.
- bsgro: убран npm-кэш, paths-ignore для md/scripts.
- Вручную: Settings → Actions → Caches / Artifacts — удалить; Billing → Usage — разбивка по репо.
