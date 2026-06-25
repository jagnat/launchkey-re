// Create MMIO memory blocks + label every peripheral register from an SVD, so the
// decompiler resolves *(0x40020810) -> GPIOC_IDR and constants show real names.
// Reads tools/svd/STM32F401.svd. Safe to re-run (skips existing blocks/labels).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.SourceType;
import org.w3c.dom.*;
import javax.xml.parsers.*;
import java.io.File;
import java.util.*;

public class LoadSvd extends GhidraScript {
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        // Two uninitialized, volatile MMIO regions covering APB1/2+AHB1 and USB OTG FS.
        ensureBlock(mem, "MMIO_periph", 0x40000000L, 0x00080000L); // 0x40000000-0x4007FFFF
        ensureBlock(mem, "MMIO_otgfs",  0x50000000L, 0x00040000L); // 0x50000000-0x5003FFFF

        File svd = new File("/Users/jagi/Programming/h4/tools/svd/STM32F401.svd");
        Document doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(svd);

        // pass 1: gather peripherals (name, base, derivedFrom, register map)
        NodeList ps = doc.getElementsByTagName("peripheral");
        LinkedHashMap<String, long[]> bases = new LinkedHashMap<>();
        Map<String, String> derived = new HashMap<>();
        Map<String, Map<String, Long>> rmap = new HashMap<>();
        for (int i = 0; i < ps.getLength(); i++) {
            Element p = (Element) ps.item(i);
            String name = child(p, "name");
            String baseS = child(p, "baseAddress");
            if (name == null || baseS == null) continue;
            long base = Long.decode(baseS.trim());
            bases.put(name, new long[]{base});
            String df = p.getAttribute("derivedFrom");
            if (df != null && !df.isEmpty()) derived.put(name, df);
            Map<String, Long> regs = new LinkedHashMap<>();
            NodeList rs = p.getElementsByTagName("register");
            for (int j = 0; j < rs.getLength(); j++) {
                Element r = (Element) rs.item(j);
                String rn = child(r, "name");
                String off = child(r, "addressOffset");
                if (rn != null && off != null) regs.put(rn, Long.decode(off.trim()));
            }
            rmap.put(name, regs);
        }

        int nlabels = 0, nbases = 0;
        for (Map.Entry<String, long[]> e : bases.entrySet()) {
            String name = e.getKey();
            long base = e.getValue()[0];
            Map<String, Long> regs = rmap.get(name);
            if ((regs == null || regs.isEmpty()) && derived.containsKey(name))
                regs = rmap.get(derived.get(name));
            // label the peripheral base
            if (label(base, name)) nbases++;
            if (regs == null) continue;
            for (Map.Entry<String, Long> r : regs.entrySet()) {
                if (label(base + r.getValue(), name + "_" + r.getKey())) nlabels++;
            }
        }
        println("LoadSvd: peripherals=" + bases.size() + " base labels=" + nbases + " register labels=" + nlabels);
    }

    void ensureBlock(Memory mem, String name, long start, long len) {
        Address a = toAddr(start);
        if (mem.getBlock(a) != null) return;
        try {
            MemoryBlock b = mem.createUninitializedBlock(name, a, len, false);
            b.setRead(true); b.setWrite(true); b.setVolatile(true);
        } catch (Exception ex) {
            println("  block " + name + " skipped: " + ex.getMessage());
        }
    }

    boolean label(long addr, String name) {
        try {
            Address a = toAddr(addr);
            if (currentProgram.getMemory().getBlock(a) == null) return false;
            // skip if a user label of this name already exists here
            for (var s : currentProgram.getSymbolTable().getSymbols(a))
                if (s.getName().equals(name)) return false;
            createLabel(a, name, true, SourceType.USER_DEFINED);
            return true;
        } catch (Exception ex) { return false; }
    }

    static String child(Element e, String tag) {
        NodeList n = e.getElementsByTagName(tag);
        for (int i = 0; i < n.getLength(); i++)
            if (n.item(i).getParentNode() == e) return n.item(i).getTextContent();
        return null;
    }
}
