import os
from subprocess import run as run_orig
from unittest import TestCase
from unittest.mock import patch

from landscape.lib import testing
from landscape.lib.security import lsof_cmd
from landscape.lib.security import awk_cmd
from landscape.lib.security import get_listeningports
from landscape.lib.security import ListeningPort


SAMPLE_LSOF_OUTPUT = """COMMAND   PID            USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
systemd     1            root   47u  IPv6 800489      0t0  TCP *:4369 (LISTEN)
systemd-n 189 systemd-network   18u  IPv4 809990      0t0  UDP 10.154.207.42:68
systemd-r 191 systemd-resolve   13u  IPv4 806291      0t0  UDP 127.0.0.53:53
systemd-r 191 systemd-resolve   14u  IPv4 806292      0t0  TCP 127.0.0.53:53 (LISTEN)
beam.smp  250        rabbitmq   18u  IPv4 808522      0t0  TCP *:25672 (LISTEN)
beam.smp  250        rabbitmq   19u  IPv4 808524      0t0  TCP 127.0.0.1:52100->127.0.0.1:4369 (ESTABLISHED)
beam.smp  250        rabbitmq   36u  IPv6 808693      0t0  TCP *:5672 (LISTEN)
beam.smp  250        rabbitmq   37u  IPv6 808734      0t0  TCP 127.0.0.1:5672->127.0.0.1:41554 (ESTABLISHED)
beam.smp  250        rabbitmq   38u  IPv6 808737      0t0  TCP 127.0.0.1:5672->127.0.0.1:41570 (ESTABLISHED)
beam.smp  250        rabbitmq   39u  IPv6 808764      0t0  TCP 127.0.0.1:5672->127.0.0.1:41582 (ESTABLISHED)
beam.smp  250        rabbitmq   40u  IPv6 808786      0t0  TCP 127.0.0.1:5672->127.0.0.1:41598 (ESTABLISHED)
beam.smp  250        rabbitmq   41u  IPv6 808803      0t0  TCP 127.0.0.1:5672->127.0.0.1:41612 (ESTABLISHED)
beam.smp  250        rabbitmq   42u  IPv6 808821      0t0  TCP 127.0.0.1:5672->127.0.0.1:41616 (ESTABLISHED)
ntpd      274             ntp   16u  IPv6 810072      0t0  UDP *:123
ntpd      274             ntp   17u  IPv4 810075      0t0  UDP *:123
ntpd      274             ntp   18u  IPv4 810079      0t0  UDP 127.0.0.1:123
ntpd      274             ntp   19u  IPv4 810081      0t0  UDP 10.154.207.42:123
ntpd      274             ntp   20u  IPv6 810083      0t0  UDP [::1]:123
ntpd      274             ntp   21u  IPv6 810085      0t0  UDP [fe80::216:3eff:fe68:1d2c]:123
apache2   279            root    4u  IPv6 799739      0t0  TCP *:80 (LISTEN)
apache2   279            root    6u  IPv6 799743      0t0  TCP *:443 (LISTEN)
sshd      287            root    3u  IPv4 805664      0t0  TCP *:22 (LISTEN)
sshd      287            root    4u  IPv6 805666      0t0  TCP *:22 (LISTEN)
apache2   292        www-data    4u  IPv6 799739      0t0  TCP *:80 (LISTEN)
apache2   292        www-data    6u  IPv6 799743      0t0  TCP *:443 (LISTEN)
apache2   293        www-data    4u  IPv6 799739      0t0  TCP *:80 (LISTEN)
apache2   293        www-data    6u  IPv6 799743      0t0  TCP *:443 (LISTEN)
postgres  412        postgres    5u  IPv4 810253      0t0  TCP 127.0.0.1:5432 (LISTEN)
postgres  412        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  444        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  445        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  446        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  447        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  448        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  449        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
epmd      528            epmd    3u  IPv6 800489      0t0  TCP *:4369 (LISTEN)
epmd      528            epmd    4u  IPv6 816421      0t0  TCP 127.0.0.1:4369->127.0.0.1:52100 (ESTABLISHED)
packagese 570       landscape    5u  IPv4 811354      0t0  TCP 127.0.0.1:42456->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape    6u  IPv4 811357      0t0  TCP 127.0.0.1:42468->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape    7u  IPv4 811361      0t0  TCP 127.0.0.1:42476->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape    8u  IPv4 811363      0t0  TCP 127.0.0.1:42488->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape    9u  IPv4 811365      0t0  TCP 127.0.0.1:42490->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   10u  IPv4 811367      0t0  TCP 127.0.0.1:42504->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   11u  IPv4 811368      0t0  TCP 127.0.0.1:42514->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   12u  IPv4 811372      0t0  TCP 127.0.0.1:42530->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   13u  IPv4 811375      0t0  TCP 127.0.0.1:42532->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   14u  IPv4 811379      0t0  TCP 127.0.0.1:42548->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   15u  IPv4 811380      0t0  TCP 127.0.0.1:42552->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   16u  IPv4 811381      0t0  TCP 127.0.0.1:42556->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   17u  IPv4 811382      0t0  TCP 127.0.0.1:42564->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   18u  IPv4 814415      0t0  TCP 127.0.0.1:42568->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   19u  IPv4 814419      0t0  TCP 127.0.0.1:42580->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   20u  IPv4 811386      0t0  TCP 127.0.0.1:42590->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   21u  IPv4 814423      0t0  TCP 127.0.0.1:42600->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   22u  IPv4 811390      0t0  TCP 127.0.0.1:42608->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   23u  IPv4 811391      0t0  TCP 127.0.0.1:42616->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   24u  IPv4 814428      0t0  TCP 127.0.0.1:42620->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   25u  IPv4 811395      0t0  TCP 127.0.0.1:42636->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   26u  IPv4 814432      0t0  TCP 127.0.0.1:42650->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   27u  IPv4 811399      0t0  TCP 127.0.0.1:42658->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   28u  IPv4 814436      0t0  TCP 127.0.0.1:42666->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   29u  IPv4 811403      0t0  TCP 127.0.0.1:42672->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   30u  IPv4 811405      0t0  TCP 127.0.0.1:42674->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   31u  IPv4 808590      0t0  TCP 127.0.0.1:42676->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   32u  IPv4 814441      0t0  TCP 127.0.0.1:42684->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   33u  IPv4 811412      0t0  TCP 127.0.0.1:42688->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   34u  IPv4 811415      0t0  TCP 127.0.0.1:42692->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   35u  IPv4 809456      0t0  TCP 127.0.0.1:42704->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   36u  IPv4 809457      0t0  TCP 127.0.0.1:42714->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   37u  IPv4 815438      0t0  TCP 127.0.0.1:42728->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   38u  IPv4 814449      0t0  TCP 127.0.0.1:42742->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   39u  IPv4 812230      0t0  TCP 127.0.0.1:42744->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   40u  IPv4 811422      0t0  TCP 127.0.0.1:42756->127.0.0.1:5432 (ESTABLISHED)
packagese 570       landscape   41u  IPv6 811426      0t0  TCP *:9099 (LISTEN)
postgres  580        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  580        postgres    8u  IPv4 809443      0t0  TCP 127.0.0.1:5432->127.0.0.1:42456 (ESTABLISHED)
postgres  581        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  581        postgres    8u  IPv4 811358      0t0  TCP 127.0.0.1:5432->127.0.0.1:42468 (ESTABLISHED)
postgres  582        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  582        postgres    8u  IPv4 811362      0t0  TCP 127.0.0.1:5432->127.0.0.1:42476 (ESTABLISHED)
postgres  585        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  585        postgres    8u  IPv4 811364      0t0  TCP 127.0.0.1:5432->127.0.0.1:42488 (ESTABLISHED)
postgres  586        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  586        postgres    8u  IPv4 811366      0t0  TCP 127.0.0.1:5432->127.0.0.1:42490 (ESTABLISHED)
postgres  587        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  587        postgres    8u  IPv4 808587      0t0  TCP 127.0.0.1:5432->127.0.0.1:42504 (ESTABLISHED)
postgres  588        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  588        postgres    8u  IPv4 811369      0t0  TCP 127.0.0.1:5432->127.0.0.1:42514 (ESTABLISHED)
postgres  589        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  589        postgres    8u  IPv4 801645      0t0  TCP 127.0.0.1:5432->127.0.0.1:42530 (ESTABLISHED)
postgres  590        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  590        postgres    8u  IPv4 801646      0t0  TCP 127.0.0.1:5432->127.0.0.1:42532 (ESTABLISHED)
postgres  593        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  593        postgres    8u  IPv4 807213      0t0  TCP 127.0.0.1:5432->127.0.0.1:42548 (ESTABLISHED)
postgres  595        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  595        postgres    8u  IPv4 808588      0t0  TCP 127.0.0.1:5432->127.0.0.1:42552 (ESTABLISHED)
postgres  597        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  597        postgres    8u  IPv4 809449      0t0  TCP 127.0.0.1:5432->127.0.0.1:42556 (ESTABLISHED)
postgres  598        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  598        postgres    8u  IPv4 814414      0t0  TCP 127.0.0.1:5432->127.0.0.1:42564 (ESTABLISHED)
postgres  599        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  599        postgres    8u  IPv4 814416      0t0  TCP 127.0.0.1:5432->127.0.0.1:42568 (ESTABLISHED)
postgres  600        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  600        postgres    8u  IPv4 811385      0t0  TCP 127.0.0.1:5432->127.0.0.1:42580 (ESTABLISHED)
postgres  601        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  601        postgres    8u  IPv4 814422      0t0  TCP 127.0.0.1:5432->127.0.0.1:42590 (ESTABLISHED)
postgres  602        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  602        postgres    8u  IPv4 811389      0t0  TCP 127.0.0.1:5432->127.0.0.1:42600 (ESTABLISHED)
postgres  603        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  603        postgres    8u  IPv4 814426      0t0  TCP 127.0.0.1:5432->127.0.0.1:42608 (ESTABLISHED)
postgres  604        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  604        postgres    8u  IPv4 814427      0t0  TCP 127.0.0.1:5432->127.0.0.1:42616 (ESTABLISHED)
postgres  605        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  605        postgres    8u  IPv4 811394      0t0  TCP 127.0.0.1:5432->127.0.0.1:42620 (ESTABLISHED)
postgres  606        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  606        postgres    8u  IPv4 814431      0t0  TCP 127.0.0.1:5432->127.0.0.1:42636 (ESTABLISHED)
postgres  607        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  607        postgres    8u  IPv4 811398      0t0  TCP 127.0.0.1:5432->127.0.0.1:42650 (ESTABLISHED)
postgres  609        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  609        postgres    8u  IPv4 814435      0t0  TCP 127.0.0.1:5432->127.0.0.1:42658 (ESTABLISHED)
postgres  610        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  610        postgres    8u  IPv4 811402      0t0  TCP 127.0.0.1:5432->127.0.0.1:42666 (ESTABLISHED)
postgres  611        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  611        postgres    8u  IPv4 811404      0t0  TCP 127.0.0.1:5432->127.0.0.1:42672 (ESTABLISHED)
postgres  612        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  612        postgres    8u  IPv4 808589      0t0  TCP 127.0.0.1:5432->127.0.0.1:42674 (ESTABLISHED)
postgres  613        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  613        postgres    8u  IPv4 811408      0t0  TCP 127.0.0.1:5432->127.0.0.1:42676 (ESTABLISHED)
postgres  614        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  614        postgres    8u  IPv4 811411      0t0  TCP 127.0.0.1:5432->127.0.0.1:42684 (ESTABLISHED)
postgres  615        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  615        postgres    8u  IPv4 814442      0t0  TCP 127.0.0.1:5432->127.0.0.1:42688 (ESTABLISHED)
postgres  616        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  616        postgres    8u  IPv4 811416      0t0  TCP 127.0.0.1:5432->127.0.0.1:42692 (ESTABLISHED)
postgres  617        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  617        postgres    8u  IPv4 814446      0t0  TCP 127.0.0.1:5432->127.0.0.1:42704 (ESTABLISHED)
postgres  618        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  618        postgres    8u  IPv4 814447      0t0  TCP 127.0.0.1:5432->127.0.0.1:42714 (ESTABLISHED)
postgres  619        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  619        postgres    8u  IPv4 814448      0t0  TCP 127.0.0.1:5432->127.0.0.1:42728 (ESTABLISHED)
postgres  620        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  620        postgres    8u  IPv4 812229      0t0  TCP 127.0.0.1:5432->127.0.0.1:42742 (ESTABLISHED)
postgres  621        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  621        postgres    8u  IPv4 814450      0t0  TCP 127.0.0.1:5432->127.0.0.1:42744 (ESTABLISHED)
postgres  622        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  622        postgres    8u  IPv4 814451      0t0  TCP 127.0.0.1:5432->127.0.0.1:42756 (ESTABLISHED)
python3   722       landscape   10u  IPv4 809560      0t0  TCP *:9100 (LISTEN)
python3   722       landscape   12u  IPv4 815502      0t0  TCP 127.0.0.1:51604->127.0.0.1:5432 (ESTABLISHED)
postgres  725        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  725        postgres    8u  IPv4 806472      0t0  TCP 127.0.0.1:5432->127.0.0.1:51604 (ESTABLISHED)
python3   727       landscape   10u  IPv4 805812      0t0  TCP *:8070 (LISTEN)
python3   727       landscape   11u  IPv4 811692      0t0  TCP 127.0.0.1:41582->127.0.0.1:5672 (ESTABLISHED)
python3   740       landscape   11u  IPv4 814516      0t0  TCP *:8090 (LISTEN)
python3   740       landscape   12u  IPv4 817171      0t0  TCP 127.0.0.1:41570->127.0.0.1:5672 (ESTABLISHED)
sshd      748            root    4u  IPv4 815669      0t0  TCP 10.154.207.42:22->10.154.207.1:46170 (ESTABLISHED)
sshd      856          ubuntu    4u  IPv4 815669      0t0  TCP 10.154.207.42:22->10.154.207.1:46170 (ESTABLISHED)
python3   867       landscape    7u  IPv4 814793      0t0  TCP 127.0.0.1:41554->127.0.0.1:5672 (ESTABLISHED)
python3   867       landscape   11u  IPv4 816642      0t0  TCP *:8080 (LISTEN)
python3   867       landscape   13u  IPv4 813744      0t0  TCP 127.0.0.1:51676->127.0.0.1:5432 (ESTABLISHED)
python3   867       landscape   14u  IPv4 814795      0t0  TCP 127.0.0.1:51686->127.0.0.1:5432 (ESTABLISHED)
postgres  932        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  932        postgres    8u  IPv4 812343      0t0  TCP 127.0.0.1:5432->127.0.0.1:51676 (ESTABLISHED)
postgres  933        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  933        postgres    8u  IPv4 816694      0t0  TCP 127.0.0.1:5432->127.0.0.1:51686 (ESTABLISHED)
python3   970       landscape   10u  IPv4 811701      0t0  TCP *:9090 (LISTEN)
python3   970       landscape   11u  IPv4 811702      0t0  TCP 127.0.0.1:41598->127.0.0.1:5672 (ESTABLISHED)
postgres  974        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  974        postgres    8u  IPv4 813768      0t0  TCP 127.0.0.1:5432->127.0.0.1:51850 (ESTABLISHED)
python3   976       landscape    7u  IPv4 806684      0t0  TCP 127.0.0.1:51850->127.0.0.1:5432 (ESTABLISHED)
python3   976       landscape   10u  IPv4 815749      0t0  TCP 127.0.0.1:41612->127.0.0.1:5672 (ESTABLISHED)
postgres  980        postgres    7u  IPv4 810255      0t0  UDP 127.0.0.1:42868->127.0.0.1:42868
postgres  980        postgres    8u  IPv4 813769      0t0  TCP 127.0.0.1:5432->127.0.0.1:51858 (ESTABLISHED)
python3   982       landscape    7u  IPv4 806693      0t0  TCP 127.0.0.1:51858->127.0.0.1:5432 (ESTABLISHED)
python3   982       landscape   11u  IPv4 806697      0t0  TCP *:9080 (LISTEN)
python3   982       landscape   12u  IPv4 806698      0t0  TCP 127.0.0.1:41616->127.0.0.1:5672 (ESTABLISHED)"""  # noqa:E501,W291


EXPECTED_AWK_OUTPUT = """systemd 1 root IPv6 TCP 4369
systemd-r 191 systemd-resolve IPv4 TCP 53
beam.smp 250 rabbitmq IPv4 TCP 25672
beam.smp 250 rabbitmq IPv6 TCP 5672
apache2 279 root IPv6 TCP 80
apache2 279 root IPv6 TCP 443
sshd 287 root IPv4 TCP 22
sshd 287 root IPv6 TCP 22
apache2 292 www-data IPv6 TCP 80
apache2 292 www-data IPv6 TCP 443
apache2 293 www-data IPv6 TCP 80
apache2 293 www-data IPv6 TCP 443
postgres 412 postgres IPv4 TCP 5432
epmd 528 epmd IPv6 TCP 4369
packagese 570 landscape IPv6 TCP 9099
python3 722 landscape IPv4 TCP 9100
python3 727 landscape IPv4 TCP 8070
python3 740 landscape IPv4 TCP 8090
python3 867 landscape IPv4 TCP 8080
python3 970 landscape IPv4 TCP 9090
python3 982 landscape IPv4 TCP 9080"""

echo_cmd = "/usr/bin/echo"


def sample_subprocess_run(
    *args,
    **kwargs,
):
    if "lsof" in args[0][0]:
        args = ([echo_cmd, "-n", "-e", SAMPLE_LSOF_OUTPUT],)

    return run_orig(*args, **kwargs)


def sample_listening_ports():
    listening = []
    for listeningport in EXPECTED_AWK_OUTPUT.splitlines():
        args = listeningport.split(" ")
        listening.append(
            ListeningPort(
                **dict(
                    zip(["cmd", "pid", "user", "kind", "mode", "port"], args)
                )
            )
        )
    return listening


def sample_listening_ports_dict():
    return [port.dict() for port in sample_listening_ports()]


class BaseTestCase(
    testing.TwistedTestCase,
    testing.FSTestCase,
    TestCase,
):
    pass


class ListeningPortsTest(BaseTestCase):
    """Test for parsing /proc/uptime data."""

    def test_analyze_object_behaviour(self):
        listening1 = ListeningPort(
            cmd="cmd",
            pid=1234,
            user="user",
            kind="kind",
            mode="mode",
            port=5678,
        )
        listening2 = ListeningPort(
            cmd="cmd",
            pid=1234,
            user="user",
            kind="kind",
            mode="mode",
            port=5678,
        )
        self.assertEqual(listening1, listening2)

        listening3 = ListeningPort(
            cmd="cmdX",
            pid=1234,
            user="user",
            kind="kind",
            mode="mode",
            port=5678,
        )
        self.assertNotEqual(listening1, listening3)

    def test_cmd_exists_and_executable(self):
        assert os.access(echo_cmd, os.X_OK)
        assert os.access(lsof_cmd, os.X_OK)
        assert os.access(awk_cmd, os.X_OK)

    @patch("landscape.lib.security.subprocess.run", sample_subprocess_run)
    def test_listeningports(self):

        listening_test = sample_listening_ports()
        listening = get_listeningports()
        self.assertEqual(listening, get_listeningports())

        listening_test_dict = [port.dict() for port in listening_test]
        listening_dict = [port.dict() for port in listening]
        self.assertEqual(listening_test_dict, listening_dict)
        self.assertEqual(
            sample_listening_ports_dict(),
            listening_dict,
        )
