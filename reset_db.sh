#!/bin/bash

CODE_ROOT=$(dirname $(dirname $(dirname $(readlink -fm $0))))
source $CODE_ROOT/shared/.env

# No idea why this is needed
export DATABASE_URL=$DATABASE_URL

SERVICE="$APP_NAME--$APP_NAME"
STATUS=`systemctl is-active $SERVICE`
if [ "$STATUS" == "active" ]; then
  echo
  echo "SERVICE '$SERVICE' IS STILL RUNNING !"
  echo
  exit 1
fi

source $CODE_ROOT/pvenv/bin/activate

# First confirmation from user, otree will do another
echo -e '\033[0;31m'
echo -e 'This will destroy all data for this app!'
echo
echo -n 'Are you absolutely sure [yes/No] : '
read answer
echo

if [[ "$answer" != "yes" ]]; then
  echo -e 'Aborting...\n'
  exit 1
fi

otree resetdb


##############################################################################
# otree/models/player.py:
#     [line 25]
#     _role = Column(st.String, nullable=False, default='')
#     _role = Column(st.String(10000), nullable=False, default='')

# otree/models/session.py:
#     [line 47]
#     label = Column(st.String, nullable=True)
#     label = Column(st.String(300), nullable=True)

# otree/models/participant.py
#     [line 86]
#     _timeout_expiration_time = otree.database.FloatField()
#     _timeout_expiration_time = Column(st.Integer,)

# otree/views/abstract.py
#     [line 769]
#     participant._timeout_expiration_time = current_time + timeout_seconds
#     participant._timeout_expiration_time = \
#             int(current_time + timeout_seconds)
##############################################################################

