# Économie du modèle

Toutes les valeurs de ce document sont produites par `tools/economics.py`. Le
modèle est du code testé (`tests/test_economics.py`) plutôt qu'un tableur, pour la
même raison que la Part de Citation est calculée et non estimée : un chiffre dont
on ne peut pas montrer le calcul n'est pas un argument.

```bash
python3 tools/economics.py                    # scénario de référence, 24 mois
python3 tools/economics.py --churn 0.08       # test de rupture
python3 tools/economics.py --slots-per-month 6 --months 36
```

## 1. Unité économique

| | Valeur | Origine |
|---|---|---|
| ARPU | **660 €** | mix 50 % Socle (349 €) / 35 % Position (749 €) / 15 % Exclusif (1 490 €) |
| Coût de mesure / client / mois | 11 € | panier figé × 2 moteurs |
| Coût d'exploitation / client / mois | 120 € | distribution, mise à jour du dossier |
| **Marge brute / client / mois** | **529 €** | 80 % de l'ARPU |
| Frais d'entrée | 900 € | dont 210 € de coût de vérification |
| CAC | **2 400 €** | 100 audits × 9 € + 1 500 € de temps commercial |
| Churn mensuel | 4,0 % | ≈ 25 mois de durée de vie |
| **LTV** | **15 809 €** | marge récurrente + attribution + marge d'entrée |
| **LTV / CAC** | **6,6x** | |
| **Retour sur CAC** | **4,5 mois** | |

**Sur le CAC.** 100 audits par vente = 8 % de prise de rendez-vous × 12 % de
closing. C'est l'hypothèse la plus incertaine du modèle et la seule qui puisse le
casser : elle est donc suivie comme indicateur hebdomadaire dans
`docs/VENTE.md`, pas comme une constante.

**Sur la marge d'exploitation.** 120 €/mois de travail humain par client est la
ligne qui décide si l'entreprise reste une entreprise de logiciel ou devient une
agence déguisée. Si elle dérive au-delà de 200 €, le modèle est une agence avec
des tableaux de bord — c'est-à-dire précisément ce que nous refusons de
construire, et le signal qu'il faut automatiser la distribution ou remonter les
prix.

## 2. Trajectoire de référence

Capacité commerciale : 3 créneaux au mois 1, montée linéaire jusqu'à 10 par mois
au mois 6. Coûts fixes 21 000 €/mois.

| Mois | Clients | MRR | CA | EBITDA | Cumul |
|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 1 980 € | 4 680 € | −24 543 € | −24 543 € |
| 3 | 13 | 8 443 € | 13 663 € | −24 151 € | −73 365 € |
| 6 | 36 | 24 458 € | 33 458 € | −18 385 € | −135 788 € |
| 9 | 61 | 42 256 € | 51 256 € | −3 815 € | **−161 625 €** |
| 12 | 83 | 58 611 € | 67 611 € | 9 684 € | −145 705 € |
| 15 | 102 | 73 081 € | 82 081 € | 21 627 € | −92 443 € |
| 18 | 119 | 85 883 € | 94 883 € | 32 193 € | −6 142 € |
| 21 | 134 | 97 209 € | 106 209 € | 41 542 € | 109 389 € |
| 24 | 147 | 107 230 € | 116 230 € | 49 813 € | 250 780 € |

- **EBITDA mensuel positif : mois 10.**
- **Cumul positif : mois 19.**
- **Besoin de financement maximal : 162 k€ au mois 9.**

Plafond de la base clients à capacité constante : `10 / 0,04 = 250 clients`, soit
environ 165 k€ de MRR. Au-delà, la croissance vient de la capacité commerciale ou
de l'ARPU, pas de l'acquisition — et c'est le moment d'ouvrir la phase Cote.

## 3. Sensibilité

**Au churn**, hypothèse la plus structurante :

| Churn mensuel | Durée de vie | LTV | LTV/CAC | Cumul positif |
|---|---|---|---|---|
| 4 % (référence) | 25 mois | 15 809 € | 6,6x | mois 19 |
| 6 % | 17 mois | 10 649 € | 4,4x | mois 21 |
| 8 % | 12 mois | 8 069 € | 3,4x | mois 24 |

**Au CAC** — si la conversion est deux fois moins bonne que prévu (200 audits par
vente) : CAC 3 300 €, LTV/CAC 4,8x, retour sur CAC 6,2 mois, cumul positif au
mois 23. Dégradé, pas cassé.

Le modèle reste viable dans les deux scénarios de rupture pris isolément. La
combinaison des deux (8 % de churn *et* 200 audits par vente) donne 2,4x : c'est
la zone où il faut arrêter et revoir l'offre plutôt que pousser l'acquisition.

## 4. Ce que ces chiffres disent du modèle

**Il est contraint par la vente, pas par la demande.** Le levier n'est ni le prix
ni le produit : c'est le nombre de créneaux vendus par mois. Doubler la capacité
commerciale double l'entreprise ; doubler les prix la tue, parce que la rareté du
créneau est déjà l'argument de prix.

**Le coût marginal de mesure est négligeable (11 €).** Toute la marge se joue sur
le coût humain de la distribution et de la vérification. C'est là qu'il faut
investir en automatisation, et nulle part ailleurs.

**Les frais d'entrée sont un filtre, pas une recette.** 900 € représentent moins
de 8 % du CA sur la durée de vie, mais ils écartent les prospects qui ne signeront
jamais un récurrent. Les supprimer pour « faciliter la vente » dégraderait le
churn bien plus que ça n'augmenterait le volume.

**Le seul chiffre à surveiller chaque semaine est le taux audit → rendez-vous.**
Il pilote le CAC, le CAC pilote le besoin de financement, et le besoin de
financement décide si l'entreprise atteint le mois 19.
