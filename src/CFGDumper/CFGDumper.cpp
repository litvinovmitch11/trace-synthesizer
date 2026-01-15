#include "llvm/CodeGen/MachineBasicBlock.h"
#include "llvm/CodeGen/MachineBranchProbabilityInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineInstr.h"
#include "llvm/CodeGen/Passes.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/IR/Module.h"
#include "llvm/InitializePasses.h"
#include "llvm/Pass.h"
#include "llvm/PassRegistry.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Target/RegisterTargetPassConfigCallback.h"
#include "llvm/Target/TargetMachine.h"

using namespace llvm;

namespace {

class CFGJsonDumper : public MachineFunctionPass {
public:
  static char ID;

  CFGJsonDumper() : MachineFunctionPass(ID) {
    initializeMachineBranchProbabilityInfoWrapperPassPass(
        *PassRegistry::getPassRegistry());
  }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.setPreservesAll();
    AU.addRequired<MachineBranchProbabilityInfoWrapperPass>();
    MachineFunctionPass::getAnalysisUsage(AU);
  }

  // Хелпер для получения имени инструкции
  std::string getInstrName(const MachineInstr &MI) {
    // В реальном проходе AsmPrinter недоступен, но мы можем взять Opcode Name
    // Это требует TargetInstrInfo, который тут сложно достать без боли.
    // Поэтому будем писать просто Opcode ID или пробовать печатать.
    std::string Str;
    raw_string_ostream OS(Str);
    // MI.print(OS); // Слишком много деталей
    return "opcode_" + std::to_string(MI.getOpcode());
  }

  bool runOnMachineFunction(MachineFunction &MF) override {
    if (MF.size() == 0)
      return false;

    auto *MBPIWrapper =
        getAnalysisIfAvailable<MachineBranchProbabilityInfoWrapperPass>();
    if (!MBPIWrapper) {
      MBPIWrapper = &getAnalysis<MachineBranchProbabilityInfoWrapperPass>();
    }
    auto &MBPI = MBPIWrapper->getMBPI();

    json::Object FuncJson;
    FuncJson["function_name"] = MF.getName();
    FuncJson["module_name"] = MF.getFunction().getParent()->getSourceFileName();

    json::Array BlocksJson;
    int LayoutIndex = 0;

    for (const MachineBasicBlock &MBB : MF) {
      json::Object BlockObj;
      BlockObj["id"] = (int64_t)MBB.getNumber();
      BlockObj["layout_index"] = LayoutIndex++;
      BlockObj["name"] = MBB.getFullName();
      BlockObj["is_entry"] = (&MBB == &MF.front());
      BlockObj["alignment"] = (int64_t)MBB.getAlignment().value();

      // --- Сбор информации об инструкциях ---
      int instrCount = 0;
      std::string firstInstr = "first instr";
      std::string lastInstr = "last instr";

      for (const auto &MI : MBB) {
        if (!MI.isDebugInstr()) { // Игнорируем отладочные метки
          instrCount++;
        }
      }

      // if (!MBB.empty()) {
      //     // Это упрощение, так как names требуют TargetInstrInfo
      //     // Но мы можем сохранить хотя бы наличие
      //     // Для production-style вывода опкодов нужен доступ к
      //     TargetSubtargetInfo const TargetInstrInfo *TII =
      //     MF.getSubtarget().getInstrInfo(); if (TII) {
      //          if (instrCount > 0) firstInstr =
      //          TII->getName(MBB.front().getOpcode()).str(); if (instrCount >
      //          0) lastInstr = TII->getName(MBB.back().getOpcode()).str();
      //     }
      // }

      BlockObj["instr_count"] = instrCount;
      BlockObj["first_instr"] = firstInstr;
      BlockObj["last_instr"] = lastInstr;
      // --------------------------------------

      json::Array Successors;
      for (const MachineBasicBlock *Succ : MBB.successors()) {
        json::Object EdgeObj;
        EdgeObj["target_id"] = (int64_t)Succ->getNumber();

        BranchProbability Prob = MBPI.getEdgeProbability(&MBB, Succ);
        EdgeObj["prob"] = Prob.toDouble();

        EdgeObj["is_fallthrough"] = MBB.isLayoutSuccessor(Succ);
        Successors.push_back(std::move(EdgeObj));
      }

      BlockObj["successors"] = std::move(Successors);
      BlocksJson.push_back(std::move(BlockObj));
    }

    FuncJson["blocks"] = std::move(BlocksJson);

    std::string Filename = (MF.getName() + ".cfg.json").str();
    std::error_code EC;
    raw_fd_ostream OS(Filename, EC, sys::fs::OF_Text);
    if (!EC) {
      OS << json::Value(std::move(FuncJson));
      OS << "\n";
    } else {
      errs() << "Error opening file " << Filename << ": " << EC.message()
             << "\n";
    }

    return false;
  }
};

} // namespace

char CFGJsonDumper::ID = 0;
static RegisterPass<CFGJsonDumper> X("cfg-json-dump", "Dump CFG JSON", false,
                                     false);
static llvm::RegisterTargetPassConfigCallback
    Y([](const TargetMachine &TM, llvm::legacy::PassManagerBase &PM,
         TargetPassConfig *TPC) {
      TPC->insertPass(&llvm::UnpackMachineBundlesID, new CFGJsonDumper());
    });
