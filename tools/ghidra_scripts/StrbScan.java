// Find every byte-store to offset +0xf (the LED descriptor colour index) and try
// to read the immediate value being stored. Output -> notes/ghidra-strb0f.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class StrbScan extends GhidraScript {
    public void run() throws Exception {
        Listing listing=currentProgram.getListing();
        StringBuilder sb=new StringBuilder("# byte-stores to [reg,#0xf]\n\n");
        Set<Function> cands=new LinkedHashSet<>();
        InstructionIterator all=listing.getInstructions(true);
        // remember last small immediate moved into each register (for value guess)
        while(all.hasNext()){
            Instruction in=all.next();
            String mn=in.getMnemonicString().toLowerCase();
            String txt=in.toString();
            if(mn.startsWith("strb") && (txt.contains("#0xf]")||txt.endsWith(",#0xf]")||txt.contains(",0xf]"))){
                Function f=getFunctionContaining(in.getAddress());
                // look back up to 6 instrs for a movs of the source reg
                String guess="?";
                Instruction p=in;
                for(int i=0;i<6 && p!=null;i++){
                    p=p.getPrevious();
                    if(p==null) break;
                    String pm=p.getMnemonicString().toLowerCase();
                    if(pm.startsWith("mov")){
                        for(int oi=0;oi<p.getNumOperands();oi++){
                            Object[] ops=p.getOpObjects(oi);
                            for(Object o:ops) if(o instanceof Scalar){ guess="0x"+Long.toHexString(((Scalar)o).getUnsignedValue())+" ("+((Scalar)o).getUnsignedValue()+")"; }
                        }
                        break;
                    }
                }
                sb.append(String.format("  %s  %-30s  in %s  src_imm=%s\n",
                    in.getAddress(), txt, f!=null?f.getName():"?", guess));
                if(f!=null) cands.add(f);
            }
        }
        sb.append("\n# candidate functions ("+cands.size()+"):\n");
        for(Function f:cands) sb.append("  "+f.getName()+" @ "+f.getEntryPoint()+" ("+f.getBody().getNumAddresses()+"b)\n");
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-strb0f.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath()+"  stores="+cands.size());
    }
}
