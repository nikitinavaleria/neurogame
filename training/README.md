# Training

Папка для обучения модели

## Данные для обучения

- `training/data/events.jsonl`
- `training/data/adaptations.jsonl`
- `training/data/sessions.jsonl`

Ключевой файл для обучения: `training/data/adaptations.jsonl`.

## Запуск 

### Вариант 1 (сервер -> датасет -> обучение)

`pipeline.py`


### Вариант 2 (только обучение по готовому датасету)

`train.py`

## Текущий алгоритм

- Offline Q-learning с CQL-регуляризацией для темпа `[-1, 0, +1]`.
- Дополнительно обучаются multi-head действия по мини-играм:
  - `compare_codes`
  - `sequence_memory`
  - `rule_switch`
  - `parity_check`
  - `radar_scan`
- Итоговый `action_space`: `tempo3_task_offsets_v1`.

Пример обучения только по baseline-логам:

```bash
python -m training.train --data training/data/adaptations.jsonl --mode baseline
```


## Процесс обучения после сбора датасета
python -m training.train --data training/data/adaptations.jsonl --out game/assets/models/ppo_agent.pt --epochs 60 --batch-size 64 --mode baseline

Epoch 1 train_total=1.4795 train_td=0.1535 train_cql=1.1232 train_task=0.8107 val_total=1.3973 val_td=0.1089 val_cql=1.0845 val_task=0.8156
Epoch 2 train_total=1.4062 train_td=0.1707 train_cql=1.0380 train_task=0.7898 val_total=1.3270 val_td=0.1263 val_cql=1.0033 val_task=0.7896
Epoch 3 train_total=1.3511 train_td=0.1997 train_cql=0.9637 train_task=0.7509 val_total=1.2562 val_td=0.1398 val_cql=0.9268 val_task=0.7586
Epoch 4 train_total=1.2865 train_td=0.2028 train_cql=0.9019 train_task=0.7271 val_total=1.1810 val_td=0.1476 val_cql=0.8534 val_task=0.7198
Epoch 5 train_total=1.2005 train_td=0.2066 train_cql=0.8225 train_task=0.6858 val_total=1.0998 val_td=0.1537 val_cql=0.7786 val_task=0.6701
Epoch 6 train_total=1.1210 train_td=0.2138 train_cql=0.7508 train_task=0.6254 val_total=1.0147 val_td=0.1501 val_cql=0.7119 val_task=0.6107
Epoch 7 train_total=1.0520 train_td=0.2109 train_cql=0.7008 train_task=0.5611 val_total=0.9230 val_td=0.1328 val_cql=0.6547 val_task=0.5418
Epoch 8 train_total=0.9627 train_td=0.1931 train_cql=0.6459 train_task=0.4947 val_total=0.8260 val_td=0.1104 val_cql=0.5990 val_task=0.4664
Epoch 9 train_total=0.8751 train_td=0.1826 train_cql=0.5890 train_task=0.4144 val_total=0.7251 val_td=0.0925 val_cql=0.5361 val_task=0.3860
Epoch 10 train_total=0.7868 train_td=0.1702 train_cql=0.5320 train_task=0.3381 val_total=0.6277 val_td=0.0758 val_cql=0.4750 val_task=0.3078
Epoch 11 train_total=0.7002 train_td=0.1616 train_cql=0.4738 train_task=0.2596 val_total=0.5379 val_td=0.0648 val_cql=0.4135 val_task=0.2381
Epoch 12 train_total=0.6309 train_td=0.1611 train_cql=0.4203 train_task=0.1981 val_total=0.4589 val_td=0.0548 val_cql=0.3588 val_task=0.1808
Epoch 13 train_total=0.5722 train_td=0.1541 train_cql=0.3809 train_task=0.1484 val_total=0.3928 val_td=0.0444 val_cql=0.3143 val_task=0.1363
Epoch 14 train_total=0.5206 train_td=0.1465 train_cql=0.3459 train_task=0.1129 val_total=0.3368 val_td=0.0385 val_cql=0.2725 val_task=0.1032
Epoch 15 train_total=0.4746 train_td=0.1413 train_cql=0.3111 train_task=0.0884 val_total=0.2928 val_td=0.0337 val_cql=0.2393 val_task=0.0792
Epoch 16 train_total=0.5138 train_td=0.1734 train_cql=0.3240 train_task=0.0656 val_total=0.2599 val_td=0.0295 val_cql=0.2149 val_task=0.0621
Epoch 17 train_total=0.4155 train_td=0.1314 train_cql=0.2707 train_task=0.0537 val_total=0.2392 val_td=0.0272 val_cql=0.1992 val_task=0.0512
Epoch 18 train_total=0.3963 train_td=0.1303 train_cql=0.2551 train_task=0.0436 val_total=0.2154 val_td=0.0274 val_cql=0.1775 val_task=0.0421
Epoch 19 train_total=0.3694 train_td=0.1271 train_cql=0.2334 train_task=0.0352 val_total=0.1968 val_td=0.0253 val_cql=0.1627 val_task=0.0352
Epoch 20 train_total=0.3560 train_td=0.1232 train_cql=0.2253 train_task=0.0301 val_total=0.1828 val_td=0.0234 val_cql=0.1519 val_task=0.0301
Epoch 21 train_total=0.3429 train_td=0.1190 train_cql=0.2173 train_task=0.0263 val_total=0.1710 val_td=0.0224 val_cql=0.1421 val_task=0.0263
Epoch 22 train_total=0.4260 train_td=0.2156 train_cql=0.2047 train_task=0.0224 val_total=0.1595 val_td=0.0219 val_cql=0.1318 val_task=0.0231
Epoch 23 train_total=0.3221 train_td=0.1109 train_cql=0.2061 train_task=0.0202 val_total=0.1539 val_td=0.0196 val_cql=0.1291 val_task=0.0208
Epoch 24 train_total=0.3706 train_td=0.1382 train_cql=0.2278 train_task=0.0181 val_total=0.1450 val_td=0.0194 val_cql=0.1208 val_task=0.0190
Epoch 25 train_total=0.2978 train_td=0.1008 train_cql=0.1929 train_task=0.0164 val_total=0.1404 val_td=0.0164 val_cql=0.1195 val_task=0.0177
Epoch 26 train_total=0.2910 train_td=0.0955 train_cql=0.1916 train_task=0.0158 val_total=0.1343 val_td=0.0157 val_cql=0.1145 val_task=0.0164
Epoch 27 train_total=0.2800 train_td=0.0940 train_cql=0.1825 train_task=0.0139 val_total=0.1292 val_td=0.0156 val_cql=0.1098 val_task=0.0152
Epoch 28 train_total=0.2804 train_td=0.0920 train_cql=0.1850 train_task=0.0136 val_total=0.1254 val_td=0.0145 val_cql=0.1073 val_task=0.0142
Epoch 29 train_total=0.2758 train_td=0.0899 train_cql=0.1825 train_task=0.0135 val_total=0.1211 val_td=0.0146 val_cql=0.1032 val_task=0.0133
Epoch 30 train_total=0.2674 train_td=0.0898 train_cql=0.1747 train_task=0.0119 val_total=0.1165 val_td=0.0142 val_cql=0.0992 val_task=0.0124
Epoch 31 train_total=0.2624 train_td=0.0897 train_cql=0.1700 train_task=0.0109 val_total=0.1147 val_td=0.0135 val_cql=0.0983 val_task=0.0118
Epoch 32 train_total=0.3364 train_td=0.1217 train_cql=0.2118 train_task=0.0112 val_total=0.1144 val_td=0.0129 val_cql=0.0986 val_task=0.0115
Epoch 33 train_total=0.2566 train_td=0.0850 train_cql=0.1691 train_task=0.0103 val_total=0.1173 val_td=0.0129 val_cql=0.1015 val_task=0.0115
Epoch 34 train_total=0.2529 train_td=0.0815 train_cql=0.1688 train_task=0.0103 val_total=0.1157 val_td=0.0125 val_cql=0.1004 val_task=0.0110
Epoch 35 train_total=0.2526 train_td=0.0817 train_cql=0.1683 train_task=0.0101 val_total=0.1123 val_td=0.0123 val_cql=0.0975 val_task=0.0105
Epoch 36 train_total=0.2458 train_td=0.0802 train_cql=0.1633 train_task=0.0093 val_total=0.1103 val_td=0.0114 val_cql=0.0964 val_task=0.0099
Epoch 37 train_total=0.3306 train_td=0.1182 train_cql=0.2100 train_task=0.0096 val_total=0.1083 val_td=0.0107 val_cql=0.0952 val_task=0.0095
Epoch 38 train_total=0.2394 train_td=0.0772 train_cql=0.1601 train_task=0.0085 val_total=0.1086 val_td=0.0099 val_cql=0.0965 val_task=0.0092
Epoch 39 train_total=0.2472 train_td=0.0790 train_cql=0.1662 train_task=0.0080 val_total=0.1073 val_td=0.0091 val_cql=0.0959 val_task=0.0088
Epoch 40 train_total=0.2349 train_td=0.0728 train_cql=0.1601 train_task=0.0078 val_total=0.1052 val_td=0.0075 val_cql=0.0956 val_task=0.0085
Epoch 41 train_total=0.3399 train_td=0.1215 train_cql=0.2165 train_task=0.0074 val_total=0.1029 val_td=0.0071 val_cql=0.0937 val_task=0.0081
Epoch 42 train_total=0.2282 train_td=0.0693 train_cql=0.1572 train_task=0.0071 val_total=0.1077 val_td=0.0073 val_cql=0.0984 val_task=0.0081
Epoch 43 train_total=0.2261 train_td=0.0683 train_cql=0.1561 train_task=0.0069 val_total=0.1048 val_td=0.0071 val_cql=0.0958 val_task=0.0076
Epoch 44 train_total=0.2291 train_td=0.0689 train_cql=0.1584 train_task=0.0071 val_total=0.1010 val_td=0.0068 val_cql=0.0924 val_task=0.0072
Epoch 45 train_total=0.2266 train_td=0.0681 train_cql=0.1568 train_task=0.0067 val_total=0.0973 val_td=0.0066 val_cql=0.0891 val_task=0.0067
Epoch 46 train_total=0.2216 train_td=0.0698 train_cql=0.1504 train_task=0.0058 val_total=0.0937 val_td=0.0063 val_cql=0.0858 val_task=0.0062
Epoch 47 train_total=0.2168 train_td=0.0691 train_cql=0.1464 train_task=0.0054 val_total=0.0910 val_td=0.0066 val_cql=0.0829 val_task=0.0059
Epoch 48 train_total=0.2178 train_td=0.0674 train_cql=0.1491 train_task=0.0053 val_total=0.0911 val_td=0.0062 val_cql=0.0834 val_task=0.0057
Epoch 49 train_total=0.2185 train_td=0.0673 train_cql=0.1499 train_task=0.0053 val_total=0.0899 val_td=0.0065 val_cql=0.0820 val_task=0.0055
Epoch 50 train_total=0.2663 train_td=0.0927 train_cql=0.1723 train_task=0.0051 val_total=0.0885 val_td=0.0058 val_cql=0.0814 val_task=0.0052
Epoch 51 train_total=0.2154 train_td=0.0645 train_cql=0.1497 train_task=0.0048 val_total=0.0896 val_td=0.0062 val_cql=0.0821 val_task=0.0051
Epoch 52 train_total=0.2105 train_td=0.0647 train_cql=0.1446 train_task=0.0047 val_total=0.0878 val_td=0.0059 val_cql=0.0806 val_task=0.0049
Epoch 53 train_total=0.2097 train_td=0.0642 train_cql=0.1444 train_task=0.0046 val_total=0.0844 val_td=0.0052 val_cql=0.0780 val_task=0.0046
Epoch 54 train_total=0.2091 train_td=0.0641 train_cql=0.1439 train_task=0.0041 val_total=0.0831 val_td=0.0051 val_cql=0.0769 val_task=0.0044
Epoch 55 train_total=0.2620 train_td=0.0891 train_cql=0.1719 train_task=0.0041 val_total=0.0822 val_td=0.0049 val_cql=0.0763 val_task=0.0043
Epoch 56 train_total=0.2075 train_td=0.0615 train_cql=0.1448 train_task=0.0049 val_total=0.0874 val_td=0.0045 val_cql=0.0819 val_task=0.0044
Epoch 57 train_total=0.2016 train_td=0.0607 train_cql=0.1400 train_task=0.0039 val_total=0.0862 val_td=0.0050 val_cql=0.0801 val_task=0.0042
Epoch 58 train_total=0.2963 train_td=0.1043 train_cql=0.1911 train_task=0.0040 val_total=0.0844 val_td=0.0050 val_cql=0.0784 val_task=0.0040
Epoch 59 train_total=0.1985 train_td=0.0586 train_cql=0.1390 train_task=0.0037 val_total=0.0851 val_td=0.0051 val_cql=0.0790 val_task=0.0040
Epoch 60 train_total=0.1997 train_td=0.0585 train_cql=0.1403 train_task=0.0037 val_total=0.0848 val_td=0.0048 val_cql=0.0791 val_task=0.0038