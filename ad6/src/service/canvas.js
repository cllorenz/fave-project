var canvas;

var nodes = {};
var firewalls = {};
var tables = {};
var rules = {};

var setVisibility = function(elems,bln) {
	for (elem in elems) {
		elems[elem].set('visible',bln)
	};
};

var hide = function(elems) {
	setVisibility(elems,false);
};

var show = function(elems) {
	setVisibility(elems,true);
};

var drawNodes = function() {
	hide(firewalls);
	hide(tables);
	show(nodes);
	canvas.renderAll();
};

var drawFirewalls = function() {
	hide(nodes);
	hide(tables);
	show(firewalls);
	canvas.renderAll();
};

var drawRules = function() {
	hide(nodes);
	hide(firewalls);
	show(tables);
	canvas.renderAll();
};

var initCanvas = function() {
	console.log('Create canvas...');
	canvas = new fabric.Canvas('myCanvas');
	console.log('Start initializing nodes...');
	initNodes();
	console.log('Start initializing firewalls...');
	initFirewalls();
	console.log('Start initializing tables...');
	initTables();
	canvas.renderAll();
	console.log(nodes);
	console.log(firewalls);
	console.log(tables);
	console.log(rules);
};


var createBoxedText = function(caption) {
	var text = new fabric.Text(caption, {
		left: 3,
		top: 3,
		fontSize: 12,
	});

	var bound = text.getBoundingRect();

	var rect = new fabric.Rect({
		width: bound.width+6,
		height: bound.height+6,
		stroke: 'black',
		fill: 'rgba(0,0,0,0)',
		strokeLineJoin: 'round',
		strokeLineCap: 'round',
	});

	return new fabric.Group([rect,text], {
		left:0,
		top:0,
		lockScalingX: true,
		lockScalingY: true,
		hasRotatingPoint: false,
		visible: false
	});
};



var createNode = function(caption) {
	var node = createBoxedText(caption);
	node.item(0).set({
		shadow: {
			color: 'black',
			blur: 10,
			offsetX: 0,
			offsetY: 0
		},
	});

	return node;
};


var createFirewall = function(caption, entries) {
	var text = new fabric.Text(caption, {
		left: 6,
		top: 3,
		fontSize: 12,
	});

	var rect = new fabric.Rect({
		width: text.getWidth()+6,
		height: text.getHeight()+6,
		stroke: 'black',
		fill: 'rgba(0,0,0,0)',
		strokeLineJoin: 'round',
		strokeLineCap: 'round',
		shadow: {
			color: 'black',
			blur: 10,
			offsetX: 0,
			offsetY: 0
		},
	});

	var height = rect.getHeight()*1.2;
	var width = rect.getWidth()+6;
	for (entry in entries) {
		var entry = entries[entry];
		if (width < entry.getWidth()) {
			width = entry.getWidth();
		};

		entry.set({
			top: height,
			left: 6
		});

		height += entry.getHeight()*1.2;
	};

	rect.set({
		width: width+12,
		height: height+12
	});

	entries.unshift(rect,text);

	return new fabric.Group(entries, {
		left: 0,
		top: 0,
		lockScalingX: true,
		lockScalingY: true,
		hasRotatingPoint: false,
		visible: false
	});
};

var createTable = function(caption,entries) {
	var text = new fabric.Text(caption, {
		left: 6,
		top: 3,
		fontSize: 12,
	});

	var rect = new fabric.Rect({
		width: text.getWidth()+6,
		height: text.getHeight()+6,
		stroke: 'black',
		fill: 'rgba(0,0,0,0)',
		strokeLineJoin: 'round',
		strokeLineCap: 'round',
		shadow: {
			color: 'black',
			blur: 10,
			offsetX: 0,
			offsetY: 0
		},
	});

	var height = rect.getHeight()*1.2;
	var width = rect.getWidth()+6;
	for (entry in entries) {
		var entry = entries[entry];
		if (width < entry.getWidth()) {
			width = entry.getWidth();
		};

		entry.set({
			top: height,
			left: 6
		});

		height += entry.getHeight()*1.2;
	};

	rect.set({
		width: width+12,
		height: height+12
	});

	entries.unshift(rect,text);

	return new fabric.Group(entries, {
		left: 0,
		top: 0,
		lockScalingX: true,
		lockScalingY: true,
		hasRotatingPoint: false,
		visible: false
	});
};


var initNodes = function() {
	var node = createNode("node0\n192.168.1.1");
	var center = canvas.getCenter();
	node.set({
		left: center.left-node.getWidth()/2,
		top: center.top-node.getHeight()/2
	});
	nodes['n0'] = node;
	canvas.add(node);
};

var initFirewalls = function() {
	var t1 = createBoxedText("forward");
	var t2 = createBoxedText("fwdin");
	var t3 = createBoxedText("accept");
	var t4 = createBoxedText("drop");

	var firewall = createFirewall("n0_fw0",[t1,t2,t3,t4]);
	var center = canvas.getCenter();
	firewall.set({
		left: center.left-firewall.getWidth()/2,
		top: center.top-firewall.getHeight()/2
	});

	firewalls['n0_fw0'] = firewall;
	canvas.add(firewall);
};


var initTables = function() {
	var r1 = createBoxedText("true");

	var r2 = createBoxedText("true");
	var r3 = createBoxedText("tcp");
	var r4 = createBoxedText("true");

	var r5 = createBoxedText("accept");
	var r6 = createBoxedText("drop");

	rules['n0_fw0_forward_r0'] = r1;
	rules['n0_fw0_fwdin_r0'] = r2;
	rules['n0_fw0_fwdin_r1'] = r3;
	rules['n0_fw0_fwdin_r2'] = r4;
	rules['n0_fw0_accept_r0'] = r5;
	rules['n0_fw0_drop_r0'] = r6;

	var t1 = createTable("forward",[r1]);
	var t2 = createTable("fwdin",[r2,r3,r4]);
	var t3 = createTable("accept",[r5]);
	var t4 = createTable("drop",[r6]);

	tables["n0_fw0_forward"] = t1;
	tables["n0_fw0_fwdin"] = t2;
	tables["n0_fw0_accept"] = t3;
	tables["n0_fw0_drop"] = t4;

	var center = canvas.getCenter();
	t1.set({
		left: center.left-t2.getWidth()-t1.getWidth(),
		top: center.top-t1.getHeight()/2
	});
	t2.set({
		left: center.left-t2.getWidth()/2,
		top: center.top-t2.getHeight()/2
	});
	t3.set({
		left: center.left+t2.getWidth(),
		top: center.top-t2.getHeight()/2-t3.getHeight()/2
	});
	t4.set({
		left: center.left+t2.getWidth(),
		top: center.top+t2.getHeight()/2-t4.getHeight()/2
	});

	canvas.add(t1);
	canvas.add(t2);
	canvas.add(t3);
	canvas.add(t4);
};

