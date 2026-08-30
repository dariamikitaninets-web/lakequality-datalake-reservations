# Day 1 na macOS — tutorial krok po kroku

## Cel dnia

Uruchomić poprawny pipeline na 1000 syntetycznych rezerwacji, zrozumieć warstwy danych i wykonać ręczne kontrole SQL. Kontrolowany wariant `buggy` pozostaje na Day 2.

## Jak korzystać z instrukcji

Nie wykonuj całego dokumentu od razu. W rozmowie tutor będzie podawał jeden krok, sprawdzał rezultat i dopiero potem otwierał następny.

## Krok 1 — otwarcie projektu i kontrola lokalizacji

### Cel

Upewnić się, że Terminal pracuje w katalogu głównym projektu.

### Dlaczego

Komendy `python -m src...` i `pip install -r requirements.txt` używają ścieżek względnych. Jeżeli Terminal jest w innym katalogu, Python nie znajdzie modułu `src`, a `pip` nie znajdzie pliku wymagań.

### Instrukcja

1. Rozpakuj ZIP w Finderze.
2. Przenieś folder `lakequality-reservations` do `Documents/QA-Portfolio` lub innego stałego miejsca.
3. Otwórz Terminal.
4. Wpisz `cd` i jedną spację.
5. Przeciągnij folder `lakequality-reservations` z Findera do okna Terminala.
6. Naciśnij Enter.
7. Uruchom:

```bash
pwd
ls
```

### Komentarz techniczny

- `cd` oznacza *change directory* — zmień katalog roboczy.
- `pwd` oznacza *print working directory* — pokaż, gdzie Terminal aktualnie pracuje.
- `ls` pokazuje zawartość bieżącego katalogu.

### Oczekiwany rezultat

Ścieżka z `pwd` kończy się na `lakequality-reservations`, a `ls` pokazuje m.in.:

```text
README.md  requirements.txt  src  sql  tests  data  docs
```

### Dowód

Na tym etapie nie zapisujemy jeszcze dowodu do finalnego portfolio. Najpierw tutor sprawdzi, czy jesteś w dobrym katalogu.

## Krok 2 — preflight środowiska, EV-001

### Cel

Sprawdzić, czy programy wymagane w projekcie odpowiadają z Terminala i zapisać stan środowiska.

### Instrukcja

```bash
python3 --version
git --version
docker --version
java -version
jmeter --version
```

### Komentarz techniczny

Parametr `--version` nie uruchamia projektu i niczego nie zmienia. Pyta program wyłącznie o jego wersję. `java -version` jest wyjątkiem składniowym, ale cel pozostaje ten sam.

Na Day 1 niezbędne są Python i Git. Docker oraz JMeter jedynie potwierdzamy, ponieważ wykorzystamy je dopiero wtedy, gdy będą uzasadnione.

Jeżeli `jmeter --version` zwróci `command not found`, JMeter może być zainstalowany jako aplikacja bez skrótu w `PATH`. Nie jest to blokada Day 1.

### Oczekiwany rezultat

- Python: 3.14 w środowisku docelowym projektu;
- Git: dowolna współczesna wersja;
- Docker: komenda rozpoznana;
- Java: komenda rozpoznana;
- JMeter: wersja albo informacja wymagająca późniejszego sprawdzenia aplikacji.

### Dowód

`EV-001_preflight_versions.png` — jedno okno Terminala z komendami i wynikami. Prywatną nazwę użytkownika w ścieżce należy ukryć przed umieszczeniem screena w portfolio.

## Krok 3 — izolowane środowisko Python

### Cel

Utworzyć osobne środowisko zależności dla projektu.

### Instrukcja

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python --version
```

### Komentarz techniczny

- `python3 -m venv .venv` tworzy środowisko w ukrytym katalogu `.venv`.
- `source .venv/bin/activate` ustawia Terminal tak, aby używał Pythona i bibliotek z tego środowiska.
- `python -m pip` wywołuje `pip` przez aktualnie aktywny interpreter, co zmniejsza ryzyko instalacji do innego Pythona.
- `requirements.txt` zawiera zależności projektu i ich wersje.

Po aktywacji początek wiersza Terminala powinien zawierać `(.venv)`.

Zależności zostały zaktualizowane po preflight EV-001 do wersji posiadających gotowe pakiety dla Python 3.14. Zmiana przeszła pełną regresję 10 testów przed wydaniem v0.3.2.

## Krok 4 — generowanie danych syntetycznych, EV-002

### Cel

Utworzyć kontrolowany zestaw wejściowy zawierający zarówno dane poprawne, jak i zaplanowane przypadki negatywne.

### Instrukcja

```bash
python -m src.generate_data --rows 1000
ls -lh data/source
wc -l data/source/bookings.csv data/source/payments.jsonl data/source/offers.csv
head -n 5 data/source/bookings.csv
head -n 3 data/source/payments.jsonl
head -n 5 data/source/offers.csv
```

### Komentarz techniczny

- `python -m src.generate_data` uruchamia moduł generatora jako część pakietu `src`.
- `--rows 1000` przekazuje generatorowi oczekiwany rozmiar źródła rezerwacji.
- `ls -lh` pokazuje pliki i czytelne rozmiary.
- `wc -l` liczy linie; dla CSV pamiętaj, że jedna linia jest nagłówkiem.
- `head` pokazuje pierwsze rekordy bez otwierania całego pliku.

### Pytanie przed uruchomieniem

Czy 1000 wygenerowanych rezerwacji oznacza, że Silver musi również zawierać dokładnie 1000 rekordów? Odpowiedź: nie. Część wierszy może być nieprawidłowa, a jedna rezerwacja ma dwie wersje. Musimy jednak umieć rozliczyć każdy rekord.

## Krok 5 — pierwszy poprawny pipeline, EV-004

### Cel

Przetworzyć dane od źródeł do Gold i otrzymać decyzję jakościową.

### Instrukcja

```bash
python -m src.pipeline --mode fixed
```

### Oczekiwany rezultat dla domyślnego seeda

```text
source bookings: 1000
Silver bookings: 992
quarantine: 9
reconciliation: 0
decision: GO
```

### Jak interpretować liczby

- 1000 rezerwacji przyszło ze źródła;
- 992 aktualne i poprawne rezerwacje trafiły do Silver;
- 1 starsza wersja została poprawnie oznaczona jako zastąpiona;
- 7 rezerwacji odrzucono z kontrolowaną przyczyną;
- 992 + 1 + 7 = 1000, więc różnica reconciliacji wynosi 0;
- Quarantine ma łącznie 9 rekordów, ponieważ poza 7 rezerwacjami zawiera 2 odrzucone płatności.

### Ważne

`GO` nie oznacza, że wszystkie dane są idealne. Oznacza, że pipeline prawidłowo rozpoznał i sklasyfikował zaplanowane dane nieprawidłowe, a żadna kontrola krytyczna nie wykazała niewyjaśnionej utraty lub błędnego wyniku.

## Krok 6 — otwarcie DuckDB w DBeaverze

1. `Database` → `New Database Connection` → `DuckDB`.
2. Wskaż `<folder projektu>/data/lakequality.duckdb`.
3. Kliknij `Test Connection` → `Finish`.
4. Jeżeli pojawi się prośba o sterownik DuckDB, pobierz oficjalny driver.
5. Otwórz `SQL Editor` → `New SQL Script`.

Najważniejsze tabele:

- `bronze_bookings`, `bronze_payments`, `bronze_offers`;
- `silver_bookings`, `silver_payments`, `superseded_bookings`;
- `quarantine_records`;
- `gold_daily_revenue`;
- `quality_summary`.

Jeżeli baza zostanie zablokowana przy ponownym uruchomieniu pipeline’u, odłącz aktywne połączenie DuckDB w DBeaverze.

## Krok 7 — pięć kontroli SQL

Zapytania znajdują się w `sql/validation.sql`. Tutor będzie omawiał i uruchamiał każde osobno: wolumeny, pola wymagane, duplikaty, relacje osierocone i reconciliation.

Przed każdym zapytaniem odpowiesz:

1. Jakiego wyniku oczekuję?
2. Jaki wynik oznacza błąd?
3. Czy zapytanie wykrywa problem, czy tylko pokazuje dane?

## Krok 8 — zakończenie Day 1

Day 1 uznamy za ukończony dopiero wtedy, gdy:

- pipeline `fixed` zakończy się poprawnie;
- wyjaśnisz różnicę między Bronze, Silver, Quarantine i Gold;
- reconciliation wyniesie 0;
- pięć zapytań SQL da oczekiwane wyniki;
- dowody zostaną sprawdzone i nazwane;
- własnymi słowami wyjaśnisz, dlaczego `1000 → 992` nie oznacza automatycznie utraty danych.
