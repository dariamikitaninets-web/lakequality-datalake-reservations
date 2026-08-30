# Opis projektu po polsku — LakeQuality: Datalake Reservations

## 1. Czym jest ten projekt

To osobisty projekt symulacyjny przygotowujący do rozmowy na stanowisko Data Test Engineer. Budujemy niewielki, ale działający lokalnie przepływ danych podobny pod względem logiki QA do projektów Datalake: dane przychodzą z kilku źródeł, są przechowywane, oczyszczane, łączone, kontrolowane i przekształcane w wynik biznesowy.

W projekcie używamy wyłącznie danych syntetycznych, czyli wygenerowanych specjalnie do ćwiczenia. Nie mamy dostępu do narzędzi, danych ani architektury Sopra Steria, Nooeh lub ich klientów. Nie twierdzimy też, że odtwarzamy ich rzeczywisty projekt. Symulujemy typ obowiązków opisanych publicznie w podobnych misjach Data QA.

## 2. Fikcyjny kontekst biznesowy

Firma turystyczna sprzedaje oferty przez trzy kanały:

- własną stronę internetową;
- agencje partnerskie;
- integrację B2B API.

Każdej nocy system otrzymuje trzy zbiory:

| Źródło | Format | Co zawiera |
|---|---|---|
| Rezerwacje | CSV | identyfikator rezerwacji, klient, oferta, status, kwota i daty |
| Płatności | JSONL | identyfikator płatności, rezerwacja, status, kwota i data zapłaty |
| Oferty | CSV | kierunek, aktywność oferty i stawka prowizji |

Celem pipeline’u jest utworzenie dziennego raportu przychodów według kierunku turystycznego. Raport będzie jednak wiarygodny tylko wtedy, gdy rezerwacje, płatności i oferty są kompletne oraz zgodne.

## 3. Co oznacza pipeline

Pipeline danych to uporządkowana sekwencja etapów przetwarzania. W naszym projekcie wygląda tak:

1. **Source** — pliki wejściowe otrzymane od systemów źródłowych.
2. **Bronze** — niezmieniona kopia danych źródłowych wraz z informacją o partii i pliku.
3. **Silver** — dane oczyszczone, ujednolicone, zweryfikowane i zdeduplikowane.
4. **Quarantine** — dane, których nie można bezpiecznie wykorzystać; każdy rekord ma podany powód odrzucenia.
5. **Gold** — wynik biznesowy: dzienne przychody według kierunku.

Najważniejsza reguła brzmi: żaden rekord nie może zniknąć bez wyjaśnienia. Rezerwacja musi być zaklasyfikowana jako aktualna, zastąpiona przez nowszą wersję albo odrzucona z konkretnym kodem przyczyny.

## 4. Dlaczego istnieją warstwy Bronze, Silver i Gold

### Bronze — dowód wejścia

Bronze chroni surowe dane. Jeżeli wynik w Gold jest nieprawidłowy, możemy wrócić do tego, co rzeczywiście przyszło w danej partii. Zapisujemy m.in. `batch_id`, nazwę pliku i checksum, czyli cyfrowy odcisk pliku.

### Silver — dane gotowe do użycia

Silver zawiera rekordy poprawne technicznie i biznesowo. Tu wykonujemy normalizację, pseudonimizację klienta, kontrolę wymaganych pól i deduplikację.

### Quarantine — kontrolowane odrzucenie

Błędne dane nie są po cichu usuwane. Trafiają do Quarantine z kodem, np. `MISSING_REQUIRED`, `UNKNOWN_OFFER` albo `AMOUNT_MISMATCH`. Dzięki temu można policzyć straty, przeanalizować przyczynę i ewentualnie ponownie przetworzyć dane po poprawce.

### Gold — wynik dla biznesu

Gold nie przechowuje już technicznych szczegółów klienta. Zawiera mierniki potrzebne do raportowania: przychód brutto, prowizję, przychód netto i liczbę potwierdzonych rezerwacji.

## 5. Symulowana misja Data Test Engineer

Naszym zadaniem jest zakwalifikowanie wersji 1.1 pipeline’u przed wdrożeniem. Wersja wprowadza przetwarzanie przyrostowe i nową regułę deduplikacji.

Musimy udowodnić, że:

- wszystkie pliki zostały przyjęte;
- struktura danych jest prawidłowa;
- pola obowiązkowe są obecne;
- najnowsza wersja rezerwacji wygrywa;
- nie ma nieuzasadnionych duplikatów;
- rezerwacje są powiązane z istniejącymi ofertami i płatnościami;
- przychód liczy się tylko dla prawidłowych kombinacji statusów;
- ponowne uruchomienie tej samej partii nie zmienia wyniku;
- suma danych wejściowych zgadza się z rekordami przyjętymi, zastąpionymi i odrzuconymi;
- pipeline działa w przyjętym czasie dla większych wolumenów;
- krytyczny błąd zatrzymuje quality gate w CI/CD.

## 6. Najważniejszy kontrolowany błąd

W Day 2 celowo uruchomimy wariant `buggy`. W nim deduplikacja zachowa najstarszą wersję rezerwacji zamiast najnowszej.

Przykład:

| booking_id | status | updated_at |
|---|---|---|
| BKG-000125 | PENDING | 2026-08-20 09:00 |
| BKG-000125 | CONFIRMED | 2026-08-20 10:15 |

Prawidłowy wynik to `CONFIRMED`, ponieważ jest to nowsza wersja. Wariant błędny zachowa `PENDING`. Może to obniżyć przychód w Gold i wprowadzić biznes w błąd.

Pokażemy pełny cykl zawodowy:

`test czerwony → analiza SQL → BUG-001 → poprawka → retest → regresja zielona → aktualizacja raportu`

## 7. Jakie rodzaje testów wykonamy

| Rodzaj testu | Co sprawdzamy w naszym projekcie |
|---|---|
| Contract/schema | Czy pliki mają wymagane kolumny i poprawne typy |
| Integration | Czy rezerwacje prawidłowo łączą się z płatnościami i ofertami |
| End-to-end | Czy źródła prowadzą do poprawnego raportu Gold |
| Reconciliation | Czy liczby rekordów zgadzają się między etapami |
| Data quality | Kompletność, poprawność, unikalność, spójność i aktualność |
| Idempotency | Czy ponowne uruchomienie tej samej partii nie tworzy zmian lub duplikatów |
| Regression | Czy po poprawce wszystkie wcześniejsze kontrole nadal przechodzą |
| Performance | Jak długo trwa batch i jaka jest przepustowość dla większego wolumenu |

## 8. Narzędzia i ich rola

| Narzędzie | Rola w projekcie | Powiązanie z Twoją praktyką |
|---|---|---|
| Python | generator danych, pipeline i logika kontroli | masz już podstawy Python i `requests` |
| pytest | automatyczne testy | masz już projekt API z pytest |
| SQL | niezależna weryfikacja danych | korzystałaś z DBeavera i zapytań SQL |
| DuckDB | lokalna baza analityczna | nowy silnik, ale standardowy SQL |
| Git/GitHub | historia zmian, Issue i Pull Request | masz GitHub i wcześniejsze repozytoria |
| GitHub Actions | automatyczny quality gate | wykonywałaś już cykl failure → fix |
| GitLab CI | rozszerzenie zgodne z opisem misji | nowa platforma, podobna zasada do Actions |
| Docker/Kubernetes | opcjonalne uruchomienie joba | Docker już znasz z Selenium Grid |

## 9. Co będzie rzeczywistym dowodem

Do portfolio trafią tylko autentyczne wyniki:

- wykonana komenda i jej rezultat;
- zapytanie SQL i otrzymana odpowiedź;
- czerwony test wywołany kontrolowanym błędem;
- zapisane GitHub Issue;
- różnica kodu w Pull Request;
- zielona regresja;
- prawdziwe wykonanie CI;
- rzeczywisty pomiar czasu;
- raport jakości wygenerowany z wyników.

Założenia biznesowe, progi laboratoryjne i nieuruchomione rozszerzenia będą wyraźnie opisane jako symulacja albo propozycja.

## 10. Co ten projekt ma udowodnić rekruterowi

Nie chodzi o twierdzenie, że masz doświadczenie produkcyjne z Datalake. Projekt ma uczciwie pokazać, że:

- rozumiesz przepływ danych source-to-target;
- potrafisz zamienić ryzyko na kryterium akceptacji i test;
- używasz SQL do analizy, nie tylko do odczytu tabel;
- umiesz rozróżnić błąd danych testowych od błędu implementacji;
- potrafisz przeprowadzić cykl defektu od wykrycia do zamknięcia;
- rozumiesz rolę automatyzacji i CI/CD;
- umiesz przedstawić dowody, ryzyka i decyzję GO/NO-GO;
- uczciwie oddzielasz wykonaną praktykę od wiedzy teoretycznej.

## 11. Krótka odpowiedź po polsku

> Zbudowałam osobisty projekt symulacyjny Data QA dla przyrostowego pipeline’u rezerwacji. Dane z trzech źródeł przechodzą przez warstwy Bronze, Silver, Quarantine i Gold. Przygotowałam kryteria akceptacji oraz kontrole jakości, integracji, reconciliacji, deduplikacji, idempotencji i wydajności. Następnie pokazałam pełny cykl kontrolowanego defektu: nieudany test, analiza SQL, rejestracja błędu, poprawka, retest, regresja oraz quality gate w CI/CD. Wszystkie dane są syntetyczne, a projekt jest wyraźnie oznaczony jako osobista symulacja.

Tę samą odpowiedź przygotujemy później do mówienia po francusku i angielsku.
