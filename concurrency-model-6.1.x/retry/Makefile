######################################################################
# NSO concurrency model conflict retry example
#
# (C) 2022 Tail-f Systems
#
# See the README file for more information
######################################################################
CDB_DIR       := ncs-cdb
INITS         := $(wildcard *_init.xml)
CDB_INITS     := $(addprefix $(CDB_DIR)/,$(INITS))

include $(NCS_DIR)/src/ncs/build/include.ncs.mk

all: $(CDB_INITS) sleep.c.ccl
	for f in packages/*/src; do \
		$(MAKE) -C $$f all || exit 1; \
	done
	$(MAKE) netsim

$(CDB_DIR)/%.xml: %.xml
	rm -f $@ ; cp $< $@

netsim:
	ncs-netsim create-network ./packages/router 3 ex --dir ./netsim

clean:
	for f in packages/*/src; do \
		$(MAKE) -C $$f clean || exit 1; \
	done
	-rm -rf logs/* state/* ncs-cdb/* netsim packages/server-config *.ccl

start:
	ncs-netsim -a start
	ncs  --addloadpath .

stop:
	-ncs --stop
	-ncs-netsim stop
	@echo "##### All NSO and netsim instances stopped"

server-config-py:
	cp -r package-repository/server-config-py packages/server-config

server-config-java:
	cp -r package-repository/server-config-java packages/server-config

showcase-py: stop clean server-config-py all start
	./showcase_py.sh

showcase-java: stop clean server-config-java all start
	./showcase_java.sh
