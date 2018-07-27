#!/usr/bin/env python

import requests
import json
import sys
from flask import Flask, request, redirect, url_for
from werkzeug.utils import secure_filename
import argparse
import uuid
import urllib

BLAZEGRAPH_URI = ""
BLAZERGRAPH_PORT = 9999
BLAZEGRAPH = "http://{0}:{1}/blazegraph/"
NAMESPACE = ""
FINAL_URL = ""

behaviour_dictionary = {
    "checkHeaterFreeArea":"check_heater_area_restriction",
    "":"",
    "":""
}

semanticmap_query_dictionary = {
    "getHeaterFreeAreas":"get_heater_free_areas",
    "":"",
    "":""
}

class SemanticMapInterface(object):
    """
        this class implements all the interaction that can be done
        with the semantic map, e.g. asking for locations of areas or
        objects
    """
    def get_heater_free_areas(self):
        query = "prefix hsf: <http://data.open.ac.uk/kmi/hans/> \nSELECT ?area ?coord\n WHERE { \n\tVALUES (?areatype) { (hsf:Area) } . \n\t?area hsf:hasRestriction hsf:HeaterRestriction . \n\t?area rdf:type ?aretype . \n\t?area hsf:hasCenter ?point . \n\t?point hsf:hasCoordinate ?coord \n}"
        
        print "Performing query to getHeaterFreeAreas"
        print query
        print ""
        # TODO: query can be a general method, as well as update
        payload = {"query":query}
        payload_ecoded= urllib.urlencode(payload)
        
        r = requests.post(FINAL_URL, params=payload_ecoded, headers={"Accept":"application/json"})
        results = json.loads(r.text)

        print "Results:"
        print results
        print ""
        
        headers = results["head"]["vars"]
        instances = results["results"]["bindings"]
        
        ret = []
        
        if len(instances) > 0:
            for instance in instances:
               area = {}
               area["name"] = get_last_uri_field(instance["area"]["value"])
               coords = instance["coord"]["value"]
               x = float(coords.split("#")[0])
               y = float(coords.split("#")[1])
               # TODO: hardcoded orientation
               area["pose"] = {"position":{"x":x,"y":y,"z":0}, "orientation":{"x":0,"y":0,"z":0,"w":1}}
               
               print "Area: %s - position: x=%s y=%s z=%s" % (instance["area"]["value"], area["pose"]["position"]["x"], area["pose"]["position"]["y"], area["pose"]["position"]["z"])
               
               ret.append(area)
        
        print ""
        return ret
        
class KBUpdateManager(object):
    """
        this class is used to update the KB with all the detected
        items. Each item is associated with a category (e.g. 'object'), 
        and the updating method for a given object is called
        'add_[category]', e.g. for the category 'object', the 
        method will be 'add_object'
    """
    
    # this method is used to add a generic object with specified class and position
    def add_object(self, detection):
        
        #TODO: queries need to be organised in files
        query = "prefix geoliteral: <http://www.bigdata.com/rdf/geospatial/literals/v1#> \nprefix hsf: <http://data.open.ac.uk/kmi/hans/> \nINSERT DATA {{ \n\t{0}   \n\t\trdf:type {1} ; \n\t\trdfs:label \"{2}\" ; \n\t\thsf:hasCoordinate \"{3}#{4}\"^^geoliteral:lat-lon . \n}}" # remember double parentheses to escape 
        
        x = detection["pose"]["position"]["x"]
        y = detection["pose"]["position"]["y"]
        
        # TODO: WARNING, code added for the ISWC2018 demo video
        # every object outside the scope of the map are not added
        # used to remove outliers
        min_x = -32.6
        max_x = 24
        min_y = -18
        max_y = 5.42
        if x < min_x or x > max_x or y < min_y or y > max_y:
            print "Outside map. Not Adding."
            return None
        
        # TODO: WARNING, code added for the ISWC2018 demo video as well
        # to avoid false positive in Activity 2
        a2_min_x = -2.3
        a2_max_x = 1.75
        a2_min_y = -9.4
        a2_max_y = -4.05
        if x >= a2_min_x and x <= a2_max_x and y >= a2_min_y and y <= a2_max_y:
            print "In Area 2. Not Adding."
            return None
            
        # TODO: WARNING, code added for the ISWC2018 demo video as well
        # to add a chair in the Robotics Lab
        rl_min_x = -1.49
        rl_max_x = 2.75
        rl_min_y = -2.08
        rl_max_y = 1.35
        if x >= rl_min_x and x <= rl_max_x and y >= rl_min_y and y <= rl_max_y:
            print "In Robotics Lab. Adding the chair."
            _class = "Chair" # Heater
            rdf_type = "hsf:" + _class # hsf:Heater
            instance_id = rdf_type + "_" + str(uuid.uuid4()) # hsf:Heater_8c41cf23-4b8b-48b1-b338-c53d6c367a6a
            label = _class 
        
            query_instance = query.format(instance_id, rdf_type, label, 0.573, 0.7)
            print "Performing query to add %s at position x=%s y=%s z=0.0" % (_class, x, y)
            print query_instance
            print ""
        
        _class = detection["class"] # Heater
        rdf_type = "hsf:" + _class # hsf:Heater
        instance_id = rdf_type + "_" + str(uuid.uuid4()) # hsf:Heater_8c41cf23-4b8b-48b1-b338-c53d6c367a6a
        label = _class 
        
        query_instance = query.format(instance_id, rdf_type, label, x, y)
        print "Performing query to add %s at position x=%s y=%s z=0.0" % (_class, x, y)
        print query_instance
        print ""
        
        
        payload = {"update":query_instance}
        payload_ecoded= urllib.urlencode(payload)
        
        r = requests.post(FINAL_URL, params=payload_ecoded)
        return r

class RuleCheckingRequestManager(object):
    """
        this class implements all the methods that correspond
        to rules to be checked. Each method implements a SPARQL
        query corresponding to the related rule 
    """
    
    def RuleCheckingRequestManager(self):
        self.area_restriction_query = 'prefix hsf: <http://data.open.ac.uk/kmi/hans/> prefix geoliteral: <http://www.bigdata.com/rdf/geospatial/literals/v1#> prefix geo: <http://www.bigdata.com/rdf/geospatial#> SELECT ?area ?itemtype ?restlabel ?arealabel ?itemlabel WHERE {{ ?area hsf:hasNorthEastPoint ?nep1 . ?nep1 hsf:hasCoordinate ?ne . ?area hsf:hasSouthWestPoint ?swp1 . ?swp1 hsf:hasCoordinate ?sw . VALUES (?itemtype) {{ ({0}) }} ?item rdf:type ?itemtype . ?item rdfs:label ?itemlabel . ?area hsf:hasRestriction ?restriction . ?restriction hsf:notAllowedItems ?natype . ?restriction rdfs:label ?restlabel . ?area rdfs:label ?arealabel . FILTER(sameTerm(?natype, ?itemtype)) . SERVICE geo:search {{ ?item geo:search "inRectangle" . ?item geo:predicate hsf:hasCoordinate . ?item geo:searchDatatype geoliteral:lat-lon . ?item geo:spatialRectangleSouthWest ?sw . ?item geo:spatialRectangleNorthEast ?ne . }} }}'
    
    # this method submit a query to check whether there are objects violeting the
    # the restriction on all the defined areas
    # to be used in the future for constant checking
    def check_area_restriction(self):
        query = self.area_restriction_query.format("hsf:Heater")

    #
    def check_heater_area_restriction(self):
        print "Checking Rule02: Electric Heater Area Restriction"
        
        query = 'prefix hsf: <http://data.open.ac.uk/kmi/hans/> \nprefix geoliteral: <http://www.bigdata.com/rdf/geospatial/literals/v1#> \nprefix geo: <http://www.bigdata.com/rdf/geospatial#> \nSELECT ?area ?itemtype ?restlabel ?arealabel ?itemlabel ?restcause ?item \nWHERE { \n\t?area hsf:hasNorthEastPoint ?nep1 . \n\t?nep1 hsf:hasCoordinate ?ne . \n\t?area hsf:hasSouthWestPoint ?swp1 . \n\t?swp1 hsf:hasCoordinate ?sw . \n\tVALUES (?itemtype) { (hsf:Heater) } ?item rdf:type ?itemtype . \n\t?item rdfs:label ?itemlabel . \n\t?area hsf:hasRestriction ?restriction . \n\t?restriction hsf:notAllowedItems ?natype . \n\t?restriction rdfs:label \n\t?restlabel . \n\t?area rdfs:label \n\t?arealabel . \n\t?restriction hsf:cause ?restcause . \n\tFILTER(sameTerm(?natype, ?itemtype)) . \n\tSERVICE geo:search { \n\t\t?item geo:search "inRectangle" . \n\t\t?item geo:predicate hsf:hasCoordinate . \n\t\t?item geo:searchDatatype geoliteral:lat-lon . \n\t\t?item geo:spatialRectangleSouthWest ?sw . \n\t\t?item geo:spatialRectangleNorthEast ?ne . \n\t} \n}'
        
        print query
        print ""
        
        payload = {"query":query}
        payload_ecoded= urllib.urlencode(payload)
        
        r = requests.post(FINAL_URL, params=payload_ecoded, headers={"Accept":"application/json"})
        
        if r.status_code != 200:
            print "Error while checking heaters violating restrictions"
            return r
        
        results = json.loads(r.text)
        
        # TODO: this output can be put in a method
        headers = results["head"]["vars"]
        instances = results["results"]["bindings"]
        
        if len(instances) > 0:
            print "There are %s heater(s) violating restrictions" % len(instances)
            
            for i in range(0,len(instances)):
                print "Restriction \"%s\" violated" % instances[i]["restlabel"]["value"]
                print "The area %s %s. Heater with ID %s is inside it." % (instances[i]["arealabel"]["value"], instances[i]["restcause"]["value"], instances[i]["item"]["value"])
        else:
            print "There are no heater violating any restriction"

app = Flask(__name__)

def signal_handler(signal,frame):
    print "Closing server"
    shutdown_server()
    sys.exit(0)

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

def get_last_uri_field(uri):
    return uri[uri.rfind("/")+1:]

def initialize_workspace():
    # method to be used for initialisation
    pass

def query_semantic_map(query):
    smi = SemanticMapInterface()
    method_name = semanticmap_query_dictionary[query]
    try:
        method = getattr(smi, method_name)
    except AttributeError:
        raise NotImplementedError("Class `{}` does not implement `{}`".format(smi.__class__.__name__, method_name))

    r = method()
    return r
    
def update_kb(detection):
    # the update can be optimised. One single query instead of many queries
    
    kbum = KBUpdateManager()
    category = detection["category"]
    method_name = "add_" + category
    
    try:
        method = getattr(kbum, method_name)
    except AttributeError:
        raise NotImplementedError("Class `{}` does not implement `{}`".format(kbum.__class__.__name__, method_name))

    r = method(detection)
    return r
    
def check_rules(detection):
    rcrm = RuleCheckingRequestManager()
    method_name = behaviour_dictionary[detection["behaviour"]]
    
    try:
        behaviour_request = getattr(rcrm, method_name)
    except AttributeError:
        raise NotImplementedError("Class `{}` does not implement `{}`".format(rcrm.__class__.__name__, method_name))

    behaviour_request()

@app.route('/semanticmap-service',methods=['POST'])         
def semanticmap_service():
    # execture specific query on the semantic map
    resp = []
    res_set = {"results":{}}
    #print "semantic map service request received"
    #print request.form.keys()

    if "json" not in request.form.keys():
        resp.append("A 'json' parameter must be specified")
        resp.append(400)
    else:
        query_json = json.loads(request.form["json"])
        query_list = query_json["semantic_map_queries"]
        
        # TODO: not completely sure of this json organisation
        for query in query_list:
            cur_query_id = query["name"]
            query_type = query["query"]
            
            query_res = query_semantic_map(query_type)
            res_set["results"][cur_query_id] = query_res
            
    #r = '{"results": {"collectWaypoints":[{"name":"Activity2", "pose":{"position":{"x":-0.25, "y":-4.35, "z":0.0},"orientation":{"x":0, "y":0, "z":0, "w":1}}},{"name":"AreaA", "pose":{"position":{"x":-0.3, "y":-0.65, "z":0.0},"orientation":{"x":0, "y":0, "z":0, "w":1}}}]}}'
    resp.append(json.dumps(res_set))
    resp.append(200)
    return app.response_class(response=resp[0], status=resp[1])

@app.route('/submitsensing',methods=['POST']) 
def submitsensing():
    
    resp = []
    #print "sensing received"
    #print request.form.keys()

    if "json" not in request.form.keys():
        resp.append("A 'json' parameter must be specified")
        resp.append(400)
    else:
        detection_json = json.loads(request.form["json"])
        detection_list = detection_json["detections"]
        
        print "Received detections"
        print detection_list
        print ""
        
        # first, the kb is updated with all the detections
        for detection in detection_list:
            try:
                update_resp = update_kb(detection)
                
                # TODO: WARNING following if added for ISWC2018 demo video
                if update_resp == None:
                    continue
                elif update_resp.status_code != 200:
                    #TODO: log this
                    print "Unable to insert %s" % detection
                    print update_resp.status_code
                    print update_resp.text
                else:
                    print "Detection inserted successfully!"
                    print ""
                    
            except NotImplementedError as e:
                #TODO: log this
                print e
                exc_type, exc_obj, exc_tb = sys.exc_info()
                print "%s: %s - %s" % (exc_type, exc_obj, exc_tb)

        # second, the consistency of all the invovled rules is checked
        for detection in detection_list:
            check_rules(detection)
        
        resp.append("OK")
        resp.append(200)
        
    return app.response_class(response=resp[0], status=resp[1])
    
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='robot-reasoner-bridge')
    parser.add_argument("--bgurl", "-u", help="the URL of the blazegraph server", default="127.0.0.1", type=str)
    parser.add_argument("--bgport", "-p", help="the PORT of the blazegraph server", default=9999, type=int)
    parser.add_argument("--namespace", "-n", help="the NAMESPACE in use in the current blazegraph instance (if any)", default="", type=str)
    args = parser.parse_args()
    
    if args.bgurl == "127.0.0.1":
        print "Using default blazegraph URL %s" % args.bgurl
    if args.bgport == 9999:
        print "Using default blazegraph PORT %s" % args.bgport
    
    BLAZEGRAPH_URL = args.bgurl
    BLAZERGRAPH_PORT = args.bgport
    BLAZEGRAPH = BLAZEGRAPH.format(BLAZEGRAPH_URL, BLAZERGRAPH_PORT)
    print "Blazegraph access address: %s" % BLAZEGRAPH
    
    NAMESPACE = args.namespace
    
    print "WARNING: using hans as default namespace for debugging purposesd"
    NAMESPACE = "hans"
    
    if NAMESPACE == "":
        FINAL_URL = BLAZEGRAPH + "/sparql"
    else:
        FINAL_URL = BLAZEGRAPH + "namespace/" + NAMESPACE + "/sparql"
    
    print "Final query URL %s" % FINAL_URL
    
    if "linux" in sys.platform.lower():
        signal.signal(signal.SIGINT,signal_handler)
        
    print "Starting server"
    try:
        # we should check whether blazegraph is up an running
        initialize_workspace()
        app.run(debug=True,use_reloader=False,threaded=True,host='0.0.0.0')
    except Exception as e:
        print e
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print "Unable to start the service"
