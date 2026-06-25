// Decompile the LED-descriptor accessors and find the descriptor array base,
// then list functions that store to descriptor+0xf (the colour-index setter).
// Output -> notes/ghidra-led-desc.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.io.*;
import java.util.*;

public class LedDescriptor extends GhidraScript {
    public void run() throws Exception {
        long[] fns={0x080111aaL,0x080111e2L,0x0801127aL,0x0800bb36L,0x080141b8L};
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        Listing listing=currentProgram.getListing();
        StringBuilder sb=new StringBuilder("# LED descriptor accessors + setter hunt\n");
        for(long a:fns){
            Function f=getFunctionContaining(toAddr(a));
            if(f==null){sb.append("// none @ "+Long.toHexString(a)+"\n");continue;}
            TreeSet<Long> ram=new TreeSet<>();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();)
              for(Reference r:ii.next().getReferencesFrom()){long to=r.getToAddress().getOffset();
                if(to>=0x20000000L&&to<0x20010000L) ram.add(to);}
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+"  RAM="+hx(ram)+" ===== */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// fail\n");
        }
        // Callers of FUN_080111e2 (the descriptor getter) — anything that gets a
        // descriptor then writes its colour is a candidate "set pad colour".
        ReferenceManager rm=currentProgram.getReferenceManager();
        sb.append("\n# callers of descriptor-getter FUN_080111e2:\n");
        Set<Function> callers=new LinkedHashSet<>();
        for(Reference r:rm.getReferencesTo(toAddr(0x080111e2L))){
            Function cf=getFunctionContaining(r.getFromAddress());
            if(cf!=null){callers.add(cf); sb.append("  "+cf.getName()+" @ "+cf.getEntryPoint()+" ("+cf.getBody().getNumAddresses()+"b)\n");}
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-led-desc.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath()+"  getterCallers="+callers.size());
    }
    String hx(Collection<Long> c){StringBuilder b=new StringBuilder();for(long v:c)b.append(String.format("0x%08X ",v));return b.toString();}
}
