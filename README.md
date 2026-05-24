### HW 2

Для выполнения домашнего задания потребуется использовать симулятор ChampSim.
В качестве конфигурации по умолчанию используйте исходный JSON-конфиг ChampSim,
установив misprediction_latency = 12.
Для оценки производительности используйте часть трасс SPEC CPU 2017 из DPC-3, а именно:
• 600.perlbench_s-1273B.champsimtrace.xz
• 602.gcc_s-1850B.champsimtrace.xz
• 603.bwaves_s-2931B.champsimtrace.xz
• 605.mcf_s-1536B.champsimtrace.xz
• 607.cactuBSSN_s-2421B.champsimtrace.xz
• 619.lbm_s-2676B.champsimtrace.xz
• 620.omnetpp_s-141B.champsimtrace.xz
• 621.wrf_s-575B.champsimtrace.xz
• 623.xalancbmk_s-165B.champsimtrace.xz
• 625.x264_s-12B.champsimtrace.xz
• 627.cam4_s-490B.champsimtrace.xz
• 628.pop2_s-17B.champsimtrace.xz
• 631.deepsjeng_s-928B.champsimtrace.xz
• 638.imagick_s-10316B.champsimtrace.xz
• 641.leela_s-149B.champsimtrace.xz
• 644.nab_s-12459B.champsimtrace.xz
• 648.exchange2_s-387B.champsimtrace.xz
• 649.fotonik3d_s-1176B.champsimtrace.xz
• 654.roms_s-293B.champsimtrace.xz
• 657.xz_s-4994B.champsimtrace.xz
Ссылка на трассы: https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/. Объём,
занимаемый на диске, составляет примерно 10 ГБ.
1. Реализуйте схемы PAp, GAg и GAp. Сравните точность предсказания с бимодальным
предиктором и между собой при одинаковых или близких размерах предикторов. Соответствуют
ли полученные результаты ожиданиям? Для всех рассмотренных схем постройте графики
значений IPC и MPKI по отдельным трассам, а также приведите GMEAN значений IPC и MPKI
по всему набору трасс.


### HW 3

Используйте симулятор и трассы из второго задания.
1. Реализуйте политику замещения Pseudo-LRU для L2-кэша. Сравните производительность и
характеристики кэширования при использовании политик LRU, Pseudo-LRU и SRRIP. В
качестве метрик используйте значения IPC и miss rate для L2-кэша как по отдельным трассам,
так и в виде GMEAN по всему набору трасс. Объясните полученные результаты.
2. Реализуйте для L2-кэша политики вставки LIP (LRU Insertion Policy) и BIP (Bimodal Insertion Policy) при ϵ = 1/32. Сравните производительность и характеристики кэширования для
следующих вариантов: LRU, Pseudo-LRU, SRRIP, LRU+LIP и LRU+BIP. В качестве
метрик используйте значения IPC и miss rate для L2-кэша как по отдельным трассам, так и в
виде GMEAN по всему набору трасс. Объясните полученные результаты и укажите, в каких
случаях изменение политики вставки помогает уменьшить загрязнение кэша.
