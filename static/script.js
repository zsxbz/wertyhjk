let current = "";
let editFile = "";


// =====================
// CPU RAM
// =====================

function updateStatus(){

    fetch("/api/status")
    .then(r=>r.json())
    .then(d=>{

        document.getElementById("cpu").innerHTML=d.cpu;
        document.getElementById("ram").innerHTML=d.ram;

    });

}

setInterval(updateStatus,1000);



// =====================
// ファイル一覧
// =====================

function loadFiles(){

    fetch(
        "/api/files?path="+encodeURIComponent(current)
    )

    .then(r=>r.json())

    .then(data=>{


        let box=document.getElementById("files");

        box.innerHTML="";


        document.getElementById("path").innerHTML=
        current || "/";



        data.forEach(f=>{


            let div=document.createElement("div");


            if(f.folder){

                div.className="folder";

                div.innerHTML="📁 "+f.name;


                div.onclick=()=>{

                    if(current)
                        current += "/"+f.name;
                    else
                        current=f.name;


                    loadFiles();

                };


            }else{


                div.className="file";

                div.innerHTML="📄 "+f.name;


                div.onclick=()=>{

                    editFile=
                    current?
                    current+"/"+f.name:
                    f.name;


                    readFile();

                };


            }


            box.appendChild(div);


        });


    });


}



// =====================
// 戻る
// =====================

function back(){

    let p=current.split("/");

    p.pop();

    current=p.join("/");


    loadFiles();

}



// =====================
// 編集
// =====================

function readFile(){

    fetch(
        "/api/read?path="+encodeURIComponent(editFile)
    )

    .then(r=>r.text())

    .then(t=>{

        document.getElementById(
            "editor"
        ).value=t;

    });


}



function save(){

    fetch("/api/edit",{

        method:"POST",

        headers:{
            "Content-Type":"application/json"
        },

        body:JSON.stringify({

            path:editFile,

            text:
            document.getElementById(
                "editor"
            ).value

        })

    });


}



// =====================
// ドラッグアップロード
// =====================


let drop=
document.getElementById("drop");


drop.ondragover=e=>{

    e.preventDefault();

};



drop.ondrop=e=>{


    e.preventDefault();


    let file=
    e.dataTransfer.files[0];


    let form=new FormData();


    form.append(
        "file",
        file
    );


    form.append(
        "path",
        current
    );


    fetch(
        "/api/upload",
        {

            method:"POST",

            body:form

        }

    )
    .then(()=>loadFiles());


};




// =====================
// プロセス一覧
// =====================


function loadProcesses(){


    fetch("/api/processes")

    .then(r=>r.json())

    .then(data=>{


        let box=
        document.getElementById(
            "servers"
        );


        box.innerHTML="";



        data.forEach(p=>{


            let div=
            document.createElement("div");



            div.innerHTML=

            (p.running?"🟢":"🔴")
            +" "
            +p.name
            +" PID:"
            +p.pid
            +"<br>";


            let start=
            document.createElement("button");

            start.innerHTML="起動";


            start.onclick=()=>{

                fetch(
                "/api/start/"+p.name
                );

            };



            let stop=
            document.createElement("button");

            stop.innerHTML="停止";


            stop.onclick=()=>{

                fetch(
                "/api/stop/"+p.name
                );

            };



            let restart=
            document.createElement("button");


            restart.innerHTML="再起動";


            restart.onclick=()=>{

                fetch(
                "/api/restart/"+p.name
                );

            };



            div.appendChild(start);
            div.appendChild(stop);
            div.appendChild(restart);


            box.appendChild(div);


        });


    });


}


setInterval(
loadProcesses,
2000
);




// =====================
// ログ
// =====================

function loadLog(){


let select=
document.getElementById(
"logserver"
);


if(!select.value)
return;


fetch(
"/api/log/"+select.value
)

.then(r=>r.text())

.then(t=>{


document.getElementById(
"log"
).innerHTML=t;


});


}


setInterval(
loadLog,
1000
);



// 初期化

loadFiles();

loadProcesses();

updateStatus();
