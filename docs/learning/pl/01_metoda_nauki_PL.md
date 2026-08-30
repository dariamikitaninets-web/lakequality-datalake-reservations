# Metoda pracy z tutorem MY QA TEAM

## Stała zasada językowa

- Instrukcje, wyjaśnienia, diagnoza błędów i pytania kontrolne: **po polsku**.
- Kod, nazwy funkcji, testów, branchy, commitów i Issue: **po angielsku**.
- Dokumenty portfolio: osobne, równoległe wersje **EN i FR**.
- Krótkie odpowiedzi na rozmowę: najpierw rozumienie po polsku, potem wersja FR i EN.

## Jak wygląda każda lekcja

Tutor podaje tylko jeden bezpieczny etap naraz. Każdy etap ma sześć części:

1. **Cel** — co osiągamy.
2. **Dlaczego** — jaka jest wartość QA i biznesowa.
3. **Instrukcja** — dokładne kliknięcia albo komenda.
4. **Komentarz techniczny** — co oznacza każdy ważny element.
5. **Oczekiwany rezultat** — z czym porównujesz swój wynik.
6. **Dowód i refleksja** — jaki screen zapisujesz i jak wyjaśniasz rezultat.

Po wykonaniu kroku przesyłasz wynik lub screen. Tutor:

- sprawdza wynik;
- wyjaśnia każdą różnicę;
- pomaga naprawić problem bez pomijania nauki;
- oznacza dowód jako przyjęty dopiero po weryfikacji;
- przechodzi do kolejnego kroku.

## Zasada „najpierw przewidź, potem uruchom”

Przed istotnym testem odpowiesz krótko:

- czego oczekujesz;
- dlaczego;
- co będzie oznaczał inny wynik.

Nie chodzi o egzamin. Dzięki temu uczysz się myślenia testera, zamiast jedynie kopiować komendy.

## Zasada diagnozy

Jeżeli wynik jest inny, nie uruchamiamy przypadkowych komend. Najpierw ustalamy:

1. Na którym etapie pojawiła się różnica?
2. Czy to błąd środowiska, danych testowych, testu czy implementacji?
3. Jaki minimalny dowód rozróżnia te hipotezy?
4. Czy naprawa zmienia kod, dane, konfigurację czy oczekiwany wynik?
5. Jaki retest i regresję trzeba wykonać?

## Zasada portfolio

Screen trafia do portfolio tylko wtedy, gdy pokazuje ważną decyzję lub dowód. Nie zbieramy przypadkowych ekranów instalacji.

Każdy zaakceptowany screen otrzyma:

- identyfikator `EV-XXX`;
- tytuł EN;
- tytuł FR;
- datę i środowisko;
- commit SHA, gdy zaczniemy używać Git;
- jednozdaniową interpretację EN i FR.

## Uczciwe granice

W portfolio rozróżniamy:

- **Actually executed / Réellement exécuté** — uruchomione przez Ciebie;
- **Simulation assumption / Hypothèse de simulation** — wymyślona reguła lub próg;
- **Proposed extension / Extension proposée** — przygotowane, ale nieuruchomione.

Nigdy nie przedstawiamy publicznego narzędzia jako narzędzia wewnętrznego firmy ani projektu osobistego jako doświadczenia produkcyjnego.

## Warunek przejścia dalej

Nie musisz pamiętać całego kodu. Przed przejściem do kolejnego etapu masz umieć odpowiedzieć własnymi słowami:

1. Co właśnie zrobiłam?
2. Jakie ryzyko sprawdziłam?
3. Co oznacza otrzymany wynik?
4. Jaki byłby następny krok przy wyniku nieprawidłowym?
