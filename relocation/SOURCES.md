# Fonti e verifiche — dati per trasferirsi

Letti da Eurostat il 2026-10-09 con `python3 tools/relocation.py`. Ogni numero in `countries.json` porta con sé dataset e anno.

## Fonti

| Indicatore | Dataset | Aggiornato da Eurostat | Query |
|---|---|---|---|
| net_earnings | `earn_nt_net` | 2026-10-01 | [query](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/earn_nt_net?format=JSON&lang=EN&sinceTimePeriod=2018&currency=EUR&estruct=NET&ecase=P1_NCH_AW100&geo=IT&geo=DE&geo=AT&geo=CH&geo=ES&geo=PT&geo=FR&geo=BE&geo=NL&geo=LU&geo=PL&geo=CZ&geo=SK&geo=HU&geo=RO&geo=BG&geo=HR&geo=SI&geo=EE&geo=LV&geo=LT&geo=IE) |
| gross_earnings | `earn_nt_net` | 2026-10-01 | [query](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/earn_nt_net?format=JSON&lang=EN&sinceTimePeriod=2018&currency=EUR&estruct=GRS&ecase=P1_NCH_AW100&geo=IT&geo=DE&geo=AT&geo=CH&geo=ES&geo=PT&geo=FR&geo=BE&geo=NL&geo=LU&geo=PL&geo=CZ&geo=SK&geo=HU&geo=RO&geo=BG&geo=HR&geo=SI&geo=EE&geo=LV&geo=LT&geo=IE) |
| price_level | `prc_ppp_ind` | 2025-07-10 | [query](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_ppp_ind?format=JSON&lang=EN&sinceTimePeriod=2018&na_item=PLI_EU27_2020&ppp_cat=A01&geo=IT&geo=DE&geo=AT&geo=CH&geo=ES&geo=PT&geo=FR&geo=BE&geo=NL&geo=LU&geo=PL&geo=CZ&geo=SK&geo=HU&geo=RO&geo=BG&geo=HR&geo=SI&geo=EE&geo=LV&geo=LT&geo=IE) |
| housing_price_level | `prc_ppp_ind` | 2025-07-10 | [query](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_ppp_ind?format=JSON&lang=EN&sinceTimePeriod=2018&na_item=PLI_EU27_2020&ppp_cat=A0104&geo=IT&geo=DE&geo=AT&geo=CH&geo=ES&geo=PT&geo=FR&geo=BE&geo=NL&geo=LU&geo=PL&geo=CZ&geo=SK&geo=HU&geo=RO&geo=BG&geo=HR&geo=SI&geo=EE&geo=LV&geo=LT&geo=IE) |
| unemployment | `une_rt_a` | 2026-09-10 | [query](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_a?format=JSON&lang=EN&sinceTimePeriod=2018&age=Y15-74&sex=T&unit=PC_ACT&geo=IT&geo=DE&geo=AT&geo=CH&geo=ES&geo=PT&geo=FR&geo=BE&geo=NL&geo=LU&geo=PL&geo=CZ&geo=SK&geo=HU&geo=RO&geo=BG&geo=HR&geo=SI&geo=EE&geo=LV&geo=LT&geo=IE) |

## Registro delle verifiche

Valori scartati e lacune. Un dato che manca qui sotto resta vuoto nel prodotto: non viene stimato né sostituito.

| Indicatore | Paese / anno | Esito |
|---|---|---|
| net_earnings | IT 2024 | scartato: 2,216.11 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | DE 2024 | scartato: 2,956.91 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | AT 2024 | scartato: 3,429.91 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | ES 2024 | scartato: 2,195.92 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | PT 2024 | scartato: 1,674.90 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | PT 2025 | scartato: 21,449.05 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | FR 2024 | scartato: 2,648.69 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | BE 2024 | scartato: 3,009.25 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | NL 2024 | scartato: 3,236.54 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | LU 2024 | scartato: 4,468.22 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | PL 2024 | scartato: 1,444.99 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | CZ 2024 | scartato: 1,611.28 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | SK 2024 | scartato: 1,416.56 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | HU 2024 | scartato: 1,182.87 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | RO 2024 | scartato: 1,064.49 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | BG 2024 | scartato: 1,063.31 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | BG 2025 | scartato: 14,449.94 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | HR 2024 | scartato: 1,266.53 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | SI 2024 | scartato: 1,853.07 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | SI 2025 | scartato: 24,275.58 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | EE 2024 | scartato: 1,788.52 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | LV 2024 | scartato: 1,439.85 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | LV 2025 | scartato: 19,035.44 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | LT 2024 | scartato: 1,468.14 si discosta di oltre il 40% dagli anni vicini |
| net_earnings | IE 2024 | scartato: 3,738.97 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | IT 2024 | scartato: 3,241.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | DE 2024 | scartato: 4,665.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | AT 2024 | scartato: 5,055.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | ES 2024 | scartato: 2,838.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | PT 2024 | scartato: 2,171.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | FR 2024 | scartato: 3,636.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | BE 2024 | scartato: 4,962.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | NL 2024 | scartato: 4,787.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | LU 2024 | scartato: 6,743.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | PL 2024 | scartato: 2,007.29 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | PL 2025 | scartato: 26,628.30 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | CZ 2024 | scartato: 2,055.81 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | SK 2024 | scartato: 1,892.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | SK 2025 | scartato: 24,240.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | HU 2024 | scartato: 1,778.76 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | RO 2024 | scartato: 1,819.64 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | RO 2025 | scartato: 23,722.04 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | BG 2024 | scartato: 1,370.28 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | BG 2025 | scartato: 18,621.54 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | HR 2024 | scartato: 1,844.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | SI 2024 | scartato: 2,945.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | SI 2025 | scartato: 38,964.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | EE 2024 | scartato: 2,272.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | LV 2024 | scartato: 2,026.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | LV 2025 | scartato: 26,208.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | LT 2024 | scartato: 2,399.00 si discosta di oltre il 40% dagli anni vicini |
| gross_earnings | IE 2024 | scartato: 4,953.00 si discosta di oltre il 40% dagli anni vicini |

## Cosa non c'è ancora

- Affitti in euro al mese per città: Eurostat pubblica indici, non livelli. Il livello dei prezzi di casa e utenze è un confronto tra paesi, non un affitto.
- Burocrazia per i cittadini UE (registrazione, codice fiscale, sanità): da scrivere paese per paese dalle pagine ufficiali Your Europe e delle amministrazioni nazionali.
