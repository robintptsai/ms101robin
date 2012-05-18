BbcodeSettings = {
	nameSpace: "bbcode",
	previewParserPath:	'/preview/', // path to your BBCode parser
	onTab: {keepDefault:false, replaceWith:'\t'},
	markupSet: [
		{name:'Bold', openWith:'[b]', closeWith:'[/b]'},
		{name:'Italic', openWith:'[i]', closeWith:'[/i]'},
		{name:'Underline', openWith:'[u]', closeWith:'[/u]'},
		{name:'Delete', openWith:'[del]', closeWith:'[/del]'},
		{name:'Sub', openWith:'[sub]', closeWith:'[/sub]'},
		{name:'Sup', openWith:'[sup]', closeWith:'[/sup]'},
		{separator:'---------------' },
		{name:'Link', openWith:'[url=[![Link]!]]', closeWith:'[/url]'},
		{name:'Picture', replaceWith:'[img][![Picture address]!][/img]'},
		{name:'Flash', replaceWith:'[flash][![Flash address]!][/flash]'},
		{name:'Size', openWith:'[size=[![Text size]!]]', closeWith:'[/size]',
			dropMenu :[
				{name:'64', openWith:'[size=64]', closeWith:'[/size]' },
				{name:'48', openWith:'[size=48]', closeWith:'[/size]' },
				{name:'32', openWith:'[size=32]', closeWith:'[/size]' },
				{name:'24', openWith:'[size=24]', closeWith:'[/size]' },
				{name:'12', openWith:'[size=12]', closeWith:'[/size]' }
			]
		},
		{	name:'Colors',
			className:'colors',
			openWith:'[color=[![Color]!]]',
			closeWith:'[/color]',
				dropMenu: [
					{name:'Yellow',	openWith:'[color=yellow]', 	closeWith:'[/color]', className:"col1-1" },
					{name:'Orange',	openWith:'[color=orange]', 	closeWith:'[/color]', className:"col1-2" },
					{name:'Red', 	openWith:'[color=red]', 	closeWith:'[/color]', className:"col1-3" },

					{name:'Blue', 	openWith:'[color=blue]', 	closeWith:'[/color]', className:"col2-1" },
					{name:'Purple', openWith:'[color=purple]', 	closeWith:'[/color]', className:"col2-2" },
					{name:'Green', 	openWith:'[color=green]', 	closeWith:'[/color]', className:"col2-3" },

					{name:'White', 	openWith:'[color=white]', 	closeWith:'[/color]', className:"col3-1" },
					{name:'Gray', 	openWith:'[color=gray]', 	closeWith:'[/color]', className:"col3-2" },
					{name:'Black',	openWith:'[color=black]', 	closeWith:'[/color]', className:"col3-3" }
				]
		},
		{separator:'---------------' },
		{name:'Left align', openWith:'[align=left]', closeWith:'[/align]'},
		{name:'Center align', openWith:'[center]', closeWith:'[/center]'},
		{name:'Right align', openWith:'[align=right]', closeWith:'[/align]'},
		{name:'Bulleted list', openWith:'[list]\n[*]', closeWith:'\n[/list]'},
		{name:'Numeric list', openWith:'[list=1]\n[*]', closeWith:'\n[/list]'},
		{name:'List item', openWith:'[*]'},
		{separator:'---------------' },
		{name:'Quotes', openWith:'[quote]', closeWith:'[/quote]'},
		{name:'Code', openWith:'[code]', closeWith:'[/code]'},
		{name:'Clean', className:"clean", replaceWith:function(markitup) { return markitup.selection.replace(/\[(.*?)\]/g, "") } },
		{name:'Preview', className:"preview", call:'preview' }
	]
};