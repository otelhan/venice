#!/bin/bash
case "$1" in
    *Username*) echo "otelhan" ;;
    *Password*) read -p "Enter GitHub token: " token; echo $token ;;
esac
