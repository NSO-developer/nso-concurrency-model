######################################################################
# NSO stacked services transaction performance example
#
# See the README file for more information
######################################################################
CDB_DIR       := nso-rundir/ncs-cdb
INITS         := $(wildcard *_init.xml)
CDB_INITS     := $(addprefix $(CDB_DIR)/,$(INITS))
NDEVS         := 10

all: setup $(CDB_INITS)

$(CDB_DIR)/%.xml: %.xml
	rm -f $@ ; cp $< $@

setup:
	ncs-setup --dest nso-rundir
	cp -r package-repository/* nso-rundir/packages/
	for f in nso-rundir/packages/*/src; do \
		$(MAKE) -C $$f all || exit 1; \
	done
	ncs-netsim create-network nso-rundir/packages/router \
	           $(NDEVS) ex --dir nso-rundir/netsim
	ncs-netsim --dir nso-rundir/netsim ncs-xml-init \
	           > nso-rundir/ncs-cdb/devices.xml

clean:
	rm -rf nso-rundir

start: stop
	cd nso-rundir; \
	ncs-netsim -a start; \
	ncs -c ncs.conf
	ncs_cmd -c 'wait-start 2'
	ncs_cmd -u admin -c 'maction /devices/sync-from'

stop:
	-ncs --stop
	-ncs-netsim --dir nso-rundir/netsim -a stop
	@echo "##### All NSO and netsim instances stopped"

# Showcase using the CLI
showcase:
	./showcase.sh
