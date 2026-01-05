#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineBasicBlock.h"
#include "llvm/CodeGen/MachineBranchProbabilityInfo.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/CodeGen/Passes.h" // Важно для ID стандартных пассов
#include "llvm/InitializePasses.h"
#include "llvm/Pass.h"
#include "llvm/PassRegistry.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Debug.h"
#include "llvm/Target/RegisterTargetPassConfigCallback.h"
#include "llvm/Target/TargetMachine.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/BasicBlock.h"

using namespace llvm;

#define DEBUG_TYPE "cfg-json-dump"

namespace {

class CFGJsonDumper : public MachineFunctionPass {
public:
    static char ID;

    CFGJsonDumper() : MachineFunctionPass(ID) {
        initializeMachineBranchProbabilityInfoWrapperPassPass(*PassRegistry::getPassRegistry());
    }

    void getAnalysisUsage(AnalysisUsage &AU) const override {
        AU.setPreservesAll();
        // Запрашиваем анализ вероятностей. 
        // Если PGO данные есть, они подтянутся сюда.
        AU.addRequired<MachineBranchProbabilityInfoWrapperPass>();
        MachineFunctionPass::getAnalysisUsage(AU);
    }

    bool runOnMachineFunction(MachineFunction &MF) override {
        // Пропускаем декларации без тела (хотя в MF они редки)
        if (MF.getFunction().isDeclaration()) return false;

        // Пытаемся получить анализ
        auto *MBPIWrapper = getAnalysisIfAvailable<MachineBranchProbabilityInfoWrapperPass>();
        if (!MBPIWrapper) {
            // Если вдруг анализа нет, берем его жестко (менеджер должен был его запустить)
            MBPIWrapper = &getAnalysis<MachineBranchProbabilityInfoWrapperPass>();
        }
        auto &MBPI = MBPIWrapper->getMBPI();

        json::Object FuncJson;
        FuncJson["function_name"] = MF.getName();
        
        // Добавим метаданные о том, есть ли реальный профиль
        FuncJson["has_profile_data"] = MF.getFunction().hasProfileData();

        json::Array BlocksJson;

        for (const MachineBasicBlock &MBB : MF) {
            json::Object BlockObj;
            BlockObj["id"] = (int64_t)MBB.getNumber();
            
            // Пытаемся получить имя из IR, если оно сохранилось
            if (const BasicBlock *BB = MBB.getBasicBlock()) {
                if (BB->hasName()) {
                    BlockObj["ir_name"] = BB->getName();
                }
            }
            
            // Определяем, является ли блок "посадочным" (entry)
            BlockObj["is_entry"] = (&MBB == &MF.front());

            json::Array Successors;
            for (const MachineBasicBlock *Succ : MBB.successors()) {
                json::Object EdgeObj;
                EdgeObj["target_id"] = (int64_t)Succ->getNumber();
                
                // Получаем вероятность перехода
                BranchProbability Prob = MBPI.getEdgeProbability(&MBB, Succ);
                EdgeObj["prob_numerator"] = (int64_t)Prob.getNumerator();
                EdgeObj["prob_denominator"] = (int64_t)Prob.getDenominator();
                EdgeObj["prob_float"] = (double)Prob.getNumerator() / Prob.getDenominator();

                // Проверяем, является ли переход "проваливанием" (fallthrough)
                // Это полезно для анализа ассемблера (нет явного jmp)
                EdgeObj["is_fallthrough"] = MBB.isLayoutSuccessor(Succ);

                Successors.push_back(std::move(EdgeObj));
            }

            BlockObj["successors"] = std::move(Successors);
            BlocksJson.push_back(std::move(BlockObj));
        }

        FuncJson["blocks"] = std::move(BlocksJson);

        // --- ВЫВОД ---
        // Для продакшена лучше писать в stderr или отдельный файл, 
        // чтобы не смешиваться с выводом llc -o -
        errs() << "=== CFG JSON START ===\n";
        errs() << json::Value(std::move(FuncJson));
        errs() << "\n=== CFG JSON END ===\n";

        return false;
    }
};

} // namespace

char CFGJsonDumper::ID = 0;

// Регистрация для ручного запуска через -run-pass
static RegisterPass<CFGJsonDumper> X(
    "cfg-json-dump", 
    "Dump CFG with Probabilities in JSON", 
    false, 
    false
);

// Автоматическая регистрация в пайплайн
static llvm::RegisterTargetPassConfigCallback Y(
    [](const TargetMachine &TM, llvm::legacy::PassManagerBase &PM, TargetPassConfig *TPC) {
        // Стратегия:
        // Мы хотим запуститься ПОСЛЕ того, как IR превратился в MachineInstr,
        // но ПЕРЕД тем, как он превратится в текст ассемблера.
        // Хорошие точки: PrologEpilogInserter (создание стека) или BlockPlacement.
        
        // insertPass принимает ID пасса, ПЕРЕД которым нужно вставиться.
        // Если мы вставим ПОСЛЕ RegisterCoalescer, у нас уже будут вирт. регистры заменены на физ.
        
        // Вставляем ПОСЛЕ пролога/эпилога (когда стек уже готов).
        // TPC->insertPass требует ID пасса, перед/после которого вставлять.
        // &PrologEpilogCodeInserterID - это идентификатор стандартного пасса LLVM.
        
        TPC->insertPass(&llvm::PrologEpilogCodeInserterID, new CFGJsonDumper());
    }
);
