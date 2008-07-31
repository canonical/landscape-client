#!/bin/sh

ERROR=False

echo
echo $(date) "==> About to run client test suite on Dapper"
echo
ssh landscape@durian.canonical.com "/srv/landscape-client-testing/scripts/run_tests.sh ${1}"
if [ "$?" != 0 ]
then
    ERROR=True
    echo $(date) "ERROR running client test suite on Dapper"
else
    echo $(date) "Successfully ran client test suite on Dapper"
fi

echo
echo $(date) "==> About to run client test suite on Feisty"
echo
ssh landscape@lapsi.canonical.com "/srv/landscape-client-testing/scripts/run_tests.sh ${1}"
if [ "$?" != 0 ]
then
    ERROR=True
    echo $(date) "ERROR running client test suite on Feisty"
else
    echo $(date) "Successfully ran client test suite on Feisty"
fi

echo
echo $(date) "==> About to run client test suite on Gutsy"
echo
ssh landscape@goumi.canonical.com "/srv/landscape-client-testing/scripts/run_tests.sh ${1}"
if [ "$?" != 0 ]
then
    ERROR=True
    echo $(date) "ERROR running client test suite on Gutsy"
else
    echo $(date) "Successfully ran client test suite on Gutsy"
fi

echo
echo $(date) "==> About to run client test suite on Hardy"
echo
ssh landscape@arhat.canonical.com "/srv/landscape-client-testing/scripts/run_tests.sh ${1}"
if [ "$?" != 0 ]
then
    ERROR=True
    echo $(date) "ERROR running client test suite on Hardy"
else
    echo $(date) "Successfully ran client test suite on Hardy"
fi

if [ "$ERROR" = "True" ]
then
    exit 1
fi

