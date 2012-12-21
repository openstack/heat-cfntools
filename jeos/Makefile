IMGFAC_API=https://steveb-redhat.local:8075/imagefactory
CURL_CMD=curl -k -H "Content-Type: application/json"
POSTED := $(patsubst %.tdl,%.tdl.posted,$(wildcard *.tdl))

version:
	$(CURL_CMD) $(IMGFAC_API)
	@echo

post: $(POSTED)
$(POSTED):
	rm -f $@
	echo -n '{"base_image":{"template":' > $@
	cat $(subst .posted,,$@) | python -c 'import json,sys; json.dump(sys.stdin.read(), sys.stdout)' >> $@
	echo -n '}}' >> $@
	$(CURL_CMD) -X POST --data "@$@" $(IMGFAC_API)/base_images


clean:
	rm *.posted

base_images:
	$(CURL_CMD) $(IMGFAC_API)/base_images
	@echo

provider_images:
	$(CURL_CMD) $(IMGFAC_API)/provider_images
	@echo

plugins:
	$(CURL_CMD) $(IMGFAC_API)/plugins
	@echo