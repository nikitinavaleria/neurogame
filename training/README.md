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
Prepared dataset: raw=12632, events=11268, adaptations=1108, sessions=82
Saved: /Users/leranikitina/PycharmProjects/neurogame/training/data/events.jsonl
Saved: /Users/leranikitina/PycharmProjects/neurogame/training/data/adaptations.jsonl
Saved: /Users/leranikitina/PycharmProjects/neurogame/training/data/sessions.jsonl
Epoch 1 total=8321.4163 td=8218.0616 cql=103.0232 task=1.3261
Epoch 2 total=2488.0116 td=2432.9521 cql=54.9681 task=0.3659
Epoch 3 total=4199.4604 td=4187.5666 cql=11.8143 task=0.3186
Epoch 4 total=1955.6990 td=1947.0575 cql=8.5851 task=0.2258
Epoch 5 total=167.1929 td=158.7604 cql=8.3945 task=0.1519
Epoch 6 total=1426.4674 td=1419.1929 cql=7.2409 task=0.1345
Epoch 7 total=396.8860 td=388.9406 cql=7.9314 task=0.0557
Epoch 8 total=1462.8846 td=1454.7376 cql=8.1387 task=0.0334
Epoch 9 total=102.5496 td=94.8809 cql=7.6638 task=0.0197
Epoch 10 total=1336.3945 td=1326.8161 cql=9.5767 task=0.0065
Epoch 11 total=178.0092 td=170.3711 cql=7.6263 task=0.0474
Epoch 12 total=1522.0993 td=1515.9080 cql=6.1707 task=0.0825
Epoch 13 total=57.6663 td=50.5458 cql=7.1195 task=0.0041
Epoch 14 total=677.9551 td=671.1289 cql=6.8248 task=0.0051
Epoch 15 total=101.8007 td=95.3815 cql=6.4125 task=0.0271
Epoch 16 total=976.2389 td=968.9614 cql=7.2766 task=0.0038
Epoch 17 total=84.0191 td=77.8377 cql=6.1808 task=0.0023
Epoch 18 total=367.3025 td=361.0327 cql=6.2692 task=0.0023
Epoch 19 total=94.8517 td=89.8394 cql=5.0120 task=0.0013
Epoch 20 total=604.2870 td=598.4770 cql=5.8082 task=0.0070
Epoch 21 total=372.7102 td=367.4467 cql=5.2521 task=0.0456
Epoch 22 total=780.1612 td=774.5331 cql=5.6266 task=0.0059
Epoch 23 total=315.9212 td=309.5714 cql=6.3488 task=0.0044
Epoch 24 total=289.5560 td=284.0901 cql=5.4651 task=0.0032
Epoch 25 total=100.8824 td=95.7016 cql=5.1801 task=0.0024
Epoch 26 total=836.1816 td=830.2974 cql=5.8840 task=0.0007
Epoch 27 total=457.0655 td=451.7574 cql=5.3062 task=0.0076
Epoch 28 total=583.3515 td=577.9822 cql=5.3691 task=0.0007
Epoch 29 total=215.5040 td=204.8317 cql=10.6721 task=0.0012
Epoch 30 total=430.8728 td=426.1894 cql=4.6826 task=0.0032
Epoch 31 total=140.9633 td=136.3720 cql=4.5905 task=0.0032
Epoch 32 total=934.4164 td=929.7956 cql=4.6200 task=0.0032
Epoch 33 total=102.2637 td=97.9452 cql=4.3177 task=0.0032
Epoch 34 total=795.7521 td=791.2599 cql=4.4915 task=0.0030
Epoch 35 total=71.2458 td=67.7837 cql=3.4614 task=0.0029
Epoch 36 total=310.2934 td=306.2043 cql=4.0883 task=0.0030
Epoch 37 total=79.6964 td=75.9168 cql=3.7790 task=0.0022
Epoch 38 total=1146.8274 td=1141.6806 cql=5.1464 task=0.0019
Epoch 39 total=195.6248 td=190.6864 cql=4.9379 task=0.0019
Epoch 40 total=831.9004 td=821.3850 cql=10.5150 task=0.0015

